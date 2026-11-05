"""Integração ponta a ponta: upload CSV -> DuckDB/Parquet -> API -> worker R (lê o Parquet) -> jaspTTests.

Requer a pilha no ar:  docker compose up -d --build
Rodar:                 RUN_INTEGRATION=1 pytest tests/test_integration.py

Valores de referência calculados com stats::t.test do R sobre o mesmo CSV
(Student: t=-2.627700 df=78 p=0.0103471 | Welch: df=72.719979 p=0.0104795).
"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

API = os.getenv("API_URL", "http://localhost:8000")
FIX = Path(__file__).parent / "fixtures"
REQUEST = json.loads((FIX / "ttest_request.json").read_text())


@pytest.fixture
def dataset_id():
    r = httpx.post(f"{API}/datasets", files={"file": ("ttest.csv", (FIX / "ttest.csv").read_bytes(), "text/csv")}, timeout=60)
    assert r.status_code == 201, r.text
    ds = r.json()
    assert {c["name"]: c["measurement"] for c in ds["columns"]} == {"score": "scale", "group": "nominal"}
    yield ds["id"]
    httpx.delete(f"{API}/datasets/{ds['id']}")


def run(dataset_id, **overrides):
    body = {**REQUEST, "dataset_id": dataset_id, **overrides}
    return httpx.post(f"{API}/analyses/run", json=body, timeout=120)


def test_ttest_from_uploaded_csv_matches_r_reference(dataset_id):
    r = run(dataset_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "complete"
    rows = {row["test"]: row for row in body["results"]["ttest"]["data"]}
    assert rows["Student"]["Statistic"] == pytest.approx(-2.627700, abs=1e-6)
    assert rows["Student"]["df"] == 78
    assert rows["Student"]["p"] == pytest.approx(0.0103471, rel=1e-4)
    assert rows["Welch"]["df"] == pytest.approx(72.719979, abs=1e-6)
    assert rows["Welch"]["p"] == pytest.approx(0.0104795, rel=1e-4)


def test_sql_query_over_uploaded_dataset(dataset_id):
    r = httpx.post(f"{API}/queries/run", json={"sql": 'SELECT "group", count(*) AS n FROM ttest GROUP BY 1 ORDER BY 1'}, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [["a", 40], ["b", 40]]


def test_worker_rejects_unknown_option(dataset_id):
    r = run(dataset_id, options={**REQUEST["options"], "students": True})
    assert r.status_code == 422 and "students" in r.json()["detail"]


def test_disallowed_analysis_is_rejected(dataset_id):
    assert run(dataset_id, analysis="Anything").status_code == 422


def test_unknown_dataset_is_404():
    assert run("0" * 32).status_code == 404


def test_grouping_variable_with_too_many_levels_is_a_clean_422():
    """Erro de validação do JASP é erro do usuário: 422 com mensagem limpa (não 502 com JSON cru)."""
    csv = "score,g\n" + "\n".join(f"{i},{'abc'[i % 3]}" for i in range(30))
    r = httpx.post(f"{API}/datasets", files={"file": ("tres.csv", csv.encode(), "text/csv")}, timeout=60)
    ds = r.json()
    try:
        r = httpx.post(f"{API}/analyses/run", json={**REQUEST, "dataset_id": ds["id"], "options": {"dependent": ["score"], "group": "g"}}, timeout=120)
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert "Maximum number of levels is 2" in detail and "has 3 levels" in detail
        assert "Error when parsing options" not in detail and "{" not in detail
    finally:
        httpx.delete(f"{API}/datasets/{ds['id']}")


# =====================================================================================================
# Pool de workers, fila, cache e recuperação do motor (exigem a pilha com 2 workers: docker compose up)
# =====================================================================================================
import asyncio  # noqa: E402

WORKER = os.getenv("WORKER_URL", "http://localhost:8001")  # r-worker-1 exposto direto, só para estes testes
EXPECT_WORKERS = int(os.getenv("EXPECT_WORKERS", "2"))
FLAG_SETS = [  # opções distintas => resultados distintos => nenhum cache atrapalha a medição de paralelismo
    {}, {"descriptivesPlot": True}, {"normalityTest": True}, {"equalityOfVariancesTest": True},
    {"effectSize": True}, {"descriptives": True, "descriptivesPlot": True},
]


@pytest.fixture
def uploaded():
    r = httpx.post(f"{API}/datasets", files={"file": ("e2e-pool.csv", (FIX / "ttest.csv").read_bytes(), "text/csv")}, timeout=60)
    assert r.status_code == 201, r.text
    yield r.json()["id"]
    httpx.delete(f"{API}/datasets/{r.json()['id']}")


def status() -> dict:
    return httpx.get(f"{API}/analyses/status", timeout=10).json()


def test_the_pool_has_the_expected_number_of_workers():
    s = status()
    assert s["workers"] == EXPECT_WORKERS and s["down"] == 0


async def test_parallel_analyses_use_every_worker_and_the_overflow_waits_in_the_queue(uploaded):
    seen = {"busy": 0, "queued": 0}
    done = asyncio.Event()

    async def watch(client):
        while not done.is_set():
            s = (await client.get(f"{API}/analyses/status")).json()
            seen["busy"], seen["queued"] = max(seen["busy"], s["busy"]), max(seen["queued"], s["queued"])
            await asyncio.sleep(0.02)

    async with httpx.AsyncClient(timeout=180) as client:
        watcher = asyncio.create_task(watch(client))
        replies = await asyncio.gather(*[
            client.post(f"{API}/analyses/run", json={**REQUEST, "dataset_id": uploaded, "options": {**REQUEST["options"], **flags}})
            for flags in FLAG_SETS
        ])
        done.set()
        await watcher
    assert [r.status_code for r in replies] == [200] * len(FLAG_SETS), [r.text[:150] for r in replies]
    assert seen["busy"] == EXPECT_WORKERS  # todos os workers trabalharam ao mesmo tempo
    assert seen["queued"] >= 1  # 6 pedidos, N workers: o excedente esperou na fila (não foi rejeitado nem perdido)
    for r in replies:  # e cada resposta é a análise correta, não a de outro pedido
        rows = {row["test"]: row for row in r.json()["results"]["ttest"]["data"]}
        assert rows["Student"]["p"] == pytest.approx(0.0103471, rel=1e-4)
    assert status()["busy"] == 0 and status()["queued"] == 0  # tudo devolvido ao pool


async def test_identical_concurrent_requests_run_once_and_later_ones_come_from_cache(uploaded):
    opts = {**REQUEST["options"], "descriptives": True, "effectSize": True, "normalityTest": True, "student": True, "welch": False}
    body = {**REQUEST, "dataset_id": uploaded, "options": opts}
    before = status()
    async with httpx.AsyncClient(timeout=180) as client:
        replies = await asyncio.gather(*[client.post(f"{API}/analyses/run", json=body) for _ in range(5)])
    assert [r.status_code for r in replies] == [200] * 5
    assert all(r.json() == replies[0].json() for r in replies)
    mid = status()
    assert mid["completed"] - before["completed"] == 1  # 5 pedidos idênticos => 1 execução
    again = httpx.post(f"{API}/analyses/run", json=body, timeout=60)
    assert again.status_code == 200 and again.json() == replies[0].json()
    after = status()
    assert after["completed"] == mid["completed"]  # o 6º veio do cache: nenhum worker foi tocado
    assert after["cache"]["hits"] == mid["cache"]["hits"] + 1


def _post_worker(payload: dict, timeout: float = 120):
    return httpx.post(f"{WORKER}/run", json=payload, timeout=timeout)


def test_worker_kills_a_runaway_analysis_and_recovers_by_itself(uploaded):
    """O worker impõe o tempo limite: estourou => 504, o motor é morto e recriado, o worker não fica preso."""
    payload = {
        "analysis": "TTestIndependentSamples", "dataset_id": uploaded, "columns": ["score", "group"],
        "measurement": {"score": "scale", "group": "nominal"}, "options": REQUEST["options"],
    }
    r = _post_worker({**payload, "timeout_s": 0.05})
    assert r.status_code == 504, r.text
    assert r.json()["code"] == "timeout" and "limit" in r.json()["message"]
    # recria o motor sozinho (sem nenhuma requisição) e o /health reflete isso de verdade
    deadline = time.time() + 120
    states = set()
    while time.time() < deadline:
        h = httpx.get(f"{WORKER}/health", timeout=10).json()
        states.add(h["engine"])
        if h["engine"] == "ready":
            break
        time.sleep(1)
    assert states <= {"warming", "ready"} and h["engine"] == "ready", states
    ok = _post_worker(payload)
    assert ok.status_code == 200 and ok.json()["status"] == "complete"


def test_worker_rejects_malformed_json_with_400_not_500():
    assert httpx.post(f"{WORKER}/run", content='{quebrado', headers={"content-type": "application/json"}, timeout=30).status_code == 400
