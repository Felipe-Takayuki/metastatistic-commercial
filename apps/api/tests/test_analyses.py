import httpx
import pytest
import respx

from app.analysis_service import AnalysisFailed, get_service
from app.config import Settings, settings
from app.main import app
from app.pool import NoWorkers, QueueFull, QueueTimeout, WorkerTimeout
from conftest import SALES_CSV, upload

URL = lambda: f"{settings.r_worker_url}/run"  # noqa: E731
OK = {"status": "complete", "results": {"a": 1}}


async def req(client, ds_id, **opts):
    return await client.post("/analyses/run", json={"analysis": "TTestIndependentSamples", "dataset_id": ds_id, "options": opts})


def sent_to(route) -> dict:
    return httpx.Response(200, content=route.calls.last.request.content).json()


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


@respx.mock
async def test_worker_gets_dataset_reference_columns_measurement_and_time_limit(client):
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).respond(json=OK)
    r = await req(client, ds["id"], dependent="receita", group="regiao", extra={"terms": [["nota"]]})
    assert r.status_code == 200 and r.json()["results"] == {"a": 1}
    sent = sent_to(route)
    assert sent["dataset_id"] == ds["id"] and "dataset" not in sent  # sem dados inline
    assert sorted(sent["columns"]) == ["nota", "receita", "regiao"]  # só o que as opções citam, inclusive aninhado
    assert sent["measurement"] == {"receita": "scale", "regiao": "nominal", "nota": "ordinal"}
    assert sent["timeout_s"] == settings.analysis_timeout_s  # o limite é imposto pelo worker, que mata o motor se estourar


@respx.mock
async def test_all_columns_when_options_mention_none(client):
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).respond(json={"status": "complete", "results": {}})
    await req(client, ds["id"])
    assert sorted(sent_to(route)["columns"]) == ["dia", "id", "nota", "receita", "regiao"]


async def test_unknown_dataset_is_404_without_calling_worker(client):
    with respx.mock(assert_all_called=False) as m:
        route = m.post(URL()).respond(json=OK)
        assert (await req(client, "0" * 32)).status_code == 404
        assert not route.called


# ---- cache -----------------------------------------------------------------
@respx.mock
async def test_identical_requests_hit_the_worker_once(client):
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).respond(json=OK)
    for _ in range(3):
        assert (await req(client, ds["id"], dependent="receita", group="regiao")).json()["results"] == {"a": 1}
    assert route.call_count == 1
    await req(client, ds["id"], dependent="receita", group="regiao", student=True)  # outra opção: executa
    assert route.call_count == 2
    assert (await client.get("/analyses/status")).json()["cache"]["hits"] == 2


@respx.mock
async def test_changing_a_column_measurement_level_invalidates_the_cached_result(client):
    """Nominal -> ordinal muda o resultado da análise: o cache NÃO pode devolver o resultado antigo."""
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).respond(json=OK)
    await req(client, ds["id"], dependent="receita", group="regiao")
    await client.patch(f"/datasets/{ds['id']}", json={"measurement": {"regiao": "ordinal"}})
    await req(client, ds["id"], dependent="receita", group="regiao")
    assert route.call_count == 2
    assert sent_to(route)["measurement"]["regiao"] == "ordinal"


@respx.mock
async def test_failed_analyses_are_not_cached(client):
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).respond(422, json={"status": "error", "message": "x"})
    for _ in range(2):
        assert (await req(client, ds["id"], dependent="receita", group="regiao")).status_code == 422
    assert route.call_count == 2


# ---- tradução de erros ---------------------------------------------------------
@respx.mock
async def test_worker_4xx_is_forwarded_as_422_with_message(client):
    ds = await upload(client, SALES_CSV)
    respx.post(URL()).respond(422, json={"status": "error", "message": "unknown option(s): foo"})
    r = await req(client, ds["id"], foo=1)
    assert r.status_code == 422 and "unknown option" in r.json()["detail"]


@respx.mock
async def test_worker_5xx_is_502_with_the_reason(client):
    ds = await upload(client, SALES_CSV)
    respx.post(URL()).respond(500, json={"status": "error", "message": "boom"})
    r = await req(client, ds["id"])
    assert r.status_code == 502 and "boom" in r.json()["detail"]


@respx.mock
async def test_engine_timeout_is_504_with_a_clear_message(client):
    ds = await upload(client, SALES_CSV)
    respx.post(URL()).respond(504, json={"status": "error", "code": "timeout", "message": "analysis exceeded the 60 s limit and was stopped"})
    r = await req(client, ds["id"])
    assert r.status_code == 504 and "excedeu o limite" in r.json()["detail"]


@respx.mock
async def test_unreachable_worker_is_503_not_a_hang(client):
    ds = await upload(client, SALES_CSV)
    respx.post(URL()).mock(side_effect=httpx.ConnectError("down"))
    r = await req(client, ds["id"])
    assert r.status_code == 503 and "indisponível" in r.json()["detail"]
    r2 = await req(client, ds["id"], student=True)  # o worker está de castigo: falha de imediato, sem tentar a conexão de novo
    assert r2.status_code == 503


@respx.mock
async def test_connection_cut_mid_request_is_502_and_does_not_break_the_service(client):
    ds = await upload(client, SALES_CSV)
    route = respx.post(URL()).mock(side_effect=httpx.RemoteProtocolError("server disconnected"))
    r = await req(client, ds["id"])
    assert r.status_code == 502 and "RemoteProtocolError" in r.json()["detail"]
    route.side_effect = None  # (o side_effect tem prioridade sobre o respond: precisa ser limpo)
    route.respond(json=OK)
    assert (await req(client, ds["id"], student=True)).status_code == 200  # o slot foi devolvido


class RaisingService:
    def __init__(self, exc):
        self.exc = exc

    async def run(self, key, payload):
        raise self.exc


@pytest.mark.parametrize("exc,status", [
    (QueueFull("fila cheia"), 429),
    (QueueTimeout("esperou demais"), 503),
    (NoWorkers("sem motor"), 503),
    (WorkerTimeout("estourou"), 504),
    (AnalysisFailed(422, "motivo do usuário"), 422),
    (RuntimeError("inesperado"), 502),
])
async def test_service_errors_map_to_the_right_http_status_and_message(client, exc, status):
    ds = await upload(client, SALES_CSV)
    app.dependency_overrides[get_service] = lambda: RaisingService(exc)
    try:
        r = await req(client, ds["id"])
    finally:
        app.dependency_overrides.pop(get_service, None)
    assert r.status_code == status
    if not isinstance(exc, RuntimeError):
        assert r.json()["detail"] == str(exc)
    else:
        assert "inesperado" not in r.json()["detail"]  # detalhe interno não vaza para o cliente


# ---- status e configuração ---------------------------------------------------------
async def test_status_endpoint_describes_the_pool_and_cache(client):
    s = (await client.get("/analyses/status")).json()
    assert s["workers"] == 1 and s["busy"] == 0 and s["queued"] == 0 and s["down"] == 0
    assert s["queue_max"] == settings.analysis_queue_max and s["timeout_s"] == settings.analysis_timeout_s
    assert set(s["cache"]) == {"entries", "bytes", "hits", "misses"}


def test_worker_urls_parse_strip_and_fall_back():
    assert Settings(r_worker_url="http://a:1/", r_worker_urls="").worker_urls == ["http://a:1"]
    assert Settings(r_worker_urls=" http://w1:8000/ , http://w2:8000,, ").worker_urls == ["http://w1:8000", "http://w2:8000"]
