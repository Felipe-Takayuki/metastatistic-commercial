"""RStatisticalEngine com worker R em outra máquina (edge): token + envio do Parquet antes da análise."""
import httpx
import pytest
import respx

from app.config import settings
from app.engines.r_engine import REngineError, RStatisticalEngine

EDGE = "http://r-edge:8090"
TOKEN = "x" * 40
DS = "a" * 32
OK = {"status": "complete", "results": {"a": 1}}


@pytest.fixture
def parquet(tmp_path, monkeypatch):
    (tmp_path / "datasets").mkdir()
    path = tmp_path / "datasets" / f"{DS}.parquet"
    path.write_bytes(b"PAR1" + b"\x01" * 50 + b"PAR1")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "r_worker_token", TOKEN)
    monkeypatch.setattr(settings, "r_worker_sync_datasets", True)
    return path


@respx.mock
async def test_uploads_once_and_sends_token(parquet):
    eng = RStatisticalEngine(urls=[EDGE])
    respx.get(f"{EDGE}/datasets/{DS}").respond(404)
    put = respx.put(f"{EDGE}/datasets/{DS}").respond(201)
    run = respx.post(f"{EDGE}/run").respond(json=OK)
    assert (await eng.execute({"dataset_id": DS, "analysis": "x"}))["results"] == {"a": 1}
    assert put.calls.last.request.content == parquet.read_bytes()
    assert put.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"
    assert run.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"
    await eng.execute({"dataset_id": DS, "analysis": "y"})
    assert put.call_count == 1   # o segundo pedido só reaproveita


@respx.mock
async def test_resends_after_dataset_not_found(parquet):
    eng = RStatisticalEngine(urls=[EDGE])
    respx.get(f"{EDGE}/datasets/{DS}").respond(404)
    put = respx.put(f"{EDGE}/datasets/{DS}").respond(201)
    respx.post(f"{EDGE}/run").mock(side_effect=[httpx.Response(400, json={"message": f"dataset not found: {DS}"}), httpx.Response(200, json=OK)])
    assert (await eng.execute({"dataset_id": DS}))["status"] == "complete"
    assert put.call_count == 2


@respx.mock
async def test_rejected_token_and_unreachable_edge(parquet):
    eng = RStatisticalEngine(urls=[EDGE])
    respx.get(f"{EDGE}/datasets/{DS}").respond(401)
    with pytest.raises(REngineError, match="R_WORKER_TOKEN") as exc:
        await eng.execute({"dataset_id": DS})
    assert exc.value.status_code == 502
    respx.clear()
    respx.get(f"{EDGE}/datasets/{DS}").mock(side_effect=httpx.ConnectError("sem rota"))
    with pytest.raises(REngineError) as exc:
        await RStatisticalEngine(urls=[EDGE]).execute({"dataset_id": DS})
    assert exc.value.status_code == 503


@respx.mock
async def test_local_mode_unchanged(parquet, monkeypatch):
    monkeypatch.setattr(settings, "r_worker_sync_datasets", False)
    monkeypatch.setattr(settings, "r_worker_token", "")
    run = respx.post(f"{EDGE}/run").respond(json=OK)
    await RStatisticalEngine(urls=[EDGE]).execute({"dataset_id": DS})
    assert respx.calls.call_count == 1 and "authorization" not in run.calls.last.request.headers
