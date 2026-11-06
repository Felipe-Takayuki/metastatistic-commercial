"""Suíte completa de testes do Microsserviço de Orquestração Estatística Dual-Engine."""
import asyncio
import math
import pytest
import respx
import httpx
from httpx import ASGITransport, AsyncClient

from app.cache import ResultCache, deterministic_cache_key
from app.config import settings
from app.engines.python_engine import PythonStatisticalEngine
from app.engines.r_engine import RStatisticalEngine
from app.engines.router import EngineRouter
from app.main import app, cache, queue_mgr
from app.queue_manager import JobStatus, QueueManager


@pytest.fixture(autouse=True)
def clean_state():
    cache.clear()
    queue_mgr.reset()
    yield
    queue_mgr.reset()
    cache.clear()


# -----------------------------------------------------------------------------
# 1. Testes Unitários dos Cálculos do Engine B (Pure Python / SciPy)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_python_engine_descriptives_known_values():
    engine = PythonStatisticalEngine()
    payload = {
        "analysis": "descriptives",
        "data": {
            "score": [10.0, 20.0, 30.0, 40.0, 50.0],
        },
        "options": {"variables": ["score"]},
    }
    result = await engine.execute(payload)
    assert result["status"] == "complete"
    assert ".meta" in result["results"]

    table = result["results"]["descriptives"]
    assert table["title"] == "Estatísticas Descritivas"
    row = table["data"][0]
    assert row["variable"] == "score"
    assert row["n"] == 5
    assert row["mean"] == 30.0
    assert math.isclose(row["sd"], 15.8114, abs_tol=1e-3)
    assert row["median"] == 30.0
    assert row["variance"] == 250.0
    assert row["min"] == 10.0
    assert row["max"] == 50.0

    # Valida estrutura dos campos e notas APA
    field_names = [f["name"] for f in table["schema"]["fields"]]
    assert "mean" in field_names and "sd" in field_names and "variance" in field_names
    assert len(table["footnotes"]) >= 1


@pytest.mark.asyncio
async def test_python_engine_ttest_independent_known_values():
    engine = PythonStatisticalEngine()
    # Grupo A: média = 15.0, Grupo B: média = 23.0
    payload = {
        "analysis": "ttest_independent",
        "data": {
            "val": [12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0],
            "group": ["A", "A", "A", "A", "B", "B", "B", "B"],
        },
        "options": {
            "dependent": "val",
            "group": "group",
        },
    }
    result = await engine.execute(payload)
    assert result["status"] == "complete"
    table = result["results"]["ttest_independent"]
    row = table["data"][0]

    assert row["variable"] == "val"
    assert row["comparison"] == "A − B"
    assert row["df"] == 6
    assert row["mean_diff"] == -8.0
    assert math.isclose(row["t"], -4.3818, abs_tol=1e-3)
    assert row["p"] < 0.01
    assert math.isclose(row["cohen_d"], -3.0984, abs_tol=1e-3)
    assert row["ci_lower"] < row["ci_upper"]


@pytest.mark.asyncio
async def test_python_engine_ttest_onesample_known_values():
    engine = PythonStatisticalEngine()
    # Média = 14.0, valor de teste = 10.0 => diff = 4.0
    payload = {
        "analysis": "ttest_onesample",
        "data": {
            "score": [10.0, 12.0, 14.0, 16.0, 18.0],
        },
        "options": {
            "variables": ["score"],
            "test_value": 10.0,
        },
    }
    result = await engine.execute(payload)
    assert result["status"] == "complete"
    table = result["results"]["ttest_onesample"]
    row = table["data"][0]

    assert row["variable"] == "score"
    assert row["test_value"] == 10.0
    assert row["df"] == 4
    assert row["mean_diff"] == 4.0
    assert math.isclose(row["t"], 2.8284, abs_tol=1e-3)
    assert math.isclose(row["p"], 0.0474, abs_tol=1e-2)
    assert math.isclose(row["cohen_d"], 1.2649, abs_tol=1e-3)


@pytest.mark.asyncio
async def test_python_engine_anova_known_values():
    engine = PythonStatisticalEngine()
    # 3 grupos com 3 elementos cada
    # G1: 1, 2, 3 (m=2)
    # G2: 4, 5, 6 (m=5)
    # G3: 7, 8, 9 (m=8)
    # SS_between = 54.0, df1 = 2, MS_between = 27.0
    # SS_within = 6.0, df2 = 6, MS_within = 1.0
    # F = 27.0, eta_sq = 54/60 = 0.90
    payload = {
        "analysis": "anova",
        "data": {
            "y": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            "cond": ["g1", "g1", "g1", "g2", "g2", "g2", "g3", "g3", "g3"],
        },
        "options": {
            "dependent": "y",
            "fixed_factors": "cond",
        },
    }
    result = await engine.execute(payload)
    assert result["status"] == "complete"
    table = result["results"]["anova"]
    row_factor = table["data"][0]
    row_residuals = table["data"][1]

    assert row_factor["cases"] == "cond"
    assert row_factor["ss"] == 54.0
    assert row_factor["df"] == 2
    assert row_factor["ms"] == 27.0
    assert row_factor["f"] == 27.0
    assert row_factor["p"] < 0.005
    assert math.isclose(row_factor["p"], 0.001, abs_tol=1e-3)
    assert row_factor["eta_sq"] == 0.9

    assert row_residuals["cases"] == "Resíduos"
    assert row_residuals["ss"] == 6.0
    assert row_residuals["df"] == 6
    assert row_residuals["ms"] == 1.0


@pytest.mark.asyncio
async def test_python_engine_correlation_known_values():
    engine = PythonStatisticalEngine()
    # Relação linear perfeita positiva
    payload = {
        "analysis": "correlation",
        "data": {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            "y": [2.0, 4.0, 6.0, 8.0, 10.0],
        },
        "options": {
            "variables": ["x", "y"],
        },
    }
    result = await engine.execute(payload)
    assert result["status"] == "complete"
    table = result["results"]["correlation"]
    row = table["data"][0]

    assert row["var1"] == "x" and row["var2"] == "y"
    assert row["r"] == 1.0
    assert row["p"] == 0.0
    assert row["n"] == 5
    assert row["df"] == 3


# -----------------------------------------------------------------------------
# 2. Testes de Roteamento de Engine ('py', 'r', 'auto')
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_router_engine_selection():
    py_engine = PythonStatisticalEngine()
    r_engine = RStatisticalEngine(urls=["http://test-r-worker:8001"])
    router = EngineRouter(python_engine=py_engine, r_engine=r_engine)

    # 1. 'py' explícito para análise suportada
    eng, name = router.select_engine({"analysis": "descriptives", "engine": "py"})
    assert name == "python"

    # 2. 'py' explícito para análise não suportada deve lançar ValueError
    with pytest.raises(ValueError, match="não é suportada pelo Engine B"):
        router.select_engine({"analysis": "ContingencyTables", "engine": "py"})

    # 3. 'r' explícito
    eng, name = router.select_engine({"analysis": "descriptives", "engine": "r"})
    assert name == "r"

    # 4. 'auto' para análise suportada pelo Engine B -> python
    eng, name = router.select_engine({"analysis": "anova", "engine": "auto"})
    assert name == "python"

    # 5. 'auto' para análise suportada apenas pelo JASP/R -> r
    eng, name = router.select_engine({"analysis": "ContingencyTables", "engine": "auto"})
    assert name == "r"


# -----------------------------------------------------------------------------
# 3. Testes do Cache Determinístico
# -----------------------------------------------------------------------------
def test_deterministic_cache_key_generation():
    k1 = deterministic_cache_key("tenant_a", "anova", "ds_1", {"dependent": "y"}, ["y", "g"])
    k2 = deterministic_cache_key("tenant_a", "anova", "ds_1", {"dependent": "y"}, ["g", "y"])
    # A ordem das colunas não deve alterar a chave (é canônica)
    assert k1 == k2

    # Tenants distintos geram chaves distintas
    k3 = deterministic_cache_key("tenant_b", "anova", "ds_1", {"dependent": "y"}, ["y", "g"])
    assert k1 != k3


def test_lru_result_cache_eviction():
    c = ResultCache(max_entries=2, max_bytes=1000)
    c.put("k1", {"data": 1})
    c.put("k2", {"data": 2})

    assert c.get("k1") == {"data": 1}
    assert c.stats()["hits"] == 1

    # Inserção do 3º elemento expulsa o menos recente (k2)
    c.put("k3", {"data": 3})
    assert c.get("k2") is None
    assert c.get("k1") is not None
    assert c.get("k3") is not None


# -----------------------------------------------------------------------------
# 4. Testes do Ciclo de Vida de Jobs e API Endpoints
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["engines"]["python"]["status"] == "healthy"
        assert "queue" in data


@pytest.mark.asyncio
async def test_api_analyses_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/analyses/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "pool" in data
        assert "cache" in data
        assert "queue" in data


@pytest.mark.asyncio
async def test_api_async_job_lifecycle():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Submissão assíncrona com prioridade Enterprise/VIP
        payload = {
            "analysis": "descriptives",
            "data": {"x": [1.0, 2.0, 3.0, 4.0]},
            "options": {"variables": ["x"]},
            "engine": "py",
            "priority": "enterprise",
        }
        submit_resp = await client.post(
            "/jobs/submit",
            json=payload,
            headers={"X-Tenant-ID": "enterprise_corp", "X-Priority": "vip"},
        )
        assert submit_resp.status_code == 200
        job_data = submit_resp.json()
        job_id = job_data["job_id"]
        assert job_data["status"] == "queued"
        assert job_data["priority"] == "vip"

        # 2. Aguarda processamento via polling de status
        for _ in range(20):
            status_resp = await client.get(f"/jobs/{job_id}")
            assert status_resp.status_code == 200
            st = status_resp.json()
            if st["status"] == "completed":
                assert st["result"] is not None
                assert st["engine_used"] == "python"
                assert st["progress"] == 1.0
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("O job não completou dentro do tempo esperado.")


@pytest.mark.asyncio
async def test_api_sync_run_with_cache_hit():
    cache.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "analysis": "descriptives",
            "data": {"metric": [10.0, 20.0, 30.0]},
            "options": {"variables": ["metric"]},
            "engine": "py",
        }

        # Primeira chamada: cache MISS
        resp1 = await client.post(
            "/analyses/run",
            json=payload,
            headers={"X-Tenant-ID": "tenant_1"},
        )
        assert resp1.status_code == 200
        assert resp1.headers.get("X-Cache") == "MISS"
        assert resp1.json()["status"] == "complete"

        # Segunda chamada idêntica: cache HIT
        resp2 = await client.post(
            "/analyses/run",
            json=payload,
            headers={"X-Tenant-ID": "tenant_1"},
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("X-Cache") == "HIT"
        assert resp2.json() == resp1.json()


@pytest.mark.asyncio
async def test_api_sync_run_r_engine_forwarding():
    # Testa roteamento para R Engine com mock HTTP do worker
    r_worker_url = settings.worker_urls[0]
    async with respx.mock(assert_all_called=True) as respx_mock:
        r_mock = respx_mock.post(f"{r_worker_url}/run").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "complete",
                    "results": {
                        ".meta": [{"name": "jasp_output", "type": "table"}],
                        "jasp_output": {"data": [{"val": 42}]},
                    },
                },
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "analysis": "ContingencyTables",
                "dataset_id": "test_ds",
                "options": {},
                "engine": "r",
            }
            resp = await client.post("/analyses/run", json=payload)
            assert resp.status_code == 200
            assert resp.json()["status"] == "complete"
            assert resp.json()["results"]["jasp_output"]["data"][0]["val"] == 42
            assert r_mock.called
