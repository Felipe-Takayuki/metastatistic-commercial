"""Worker R em outra máquina: o Parquet é enviado ao edge antes da análise (apps/api/app/remote_datasets.py)."""
import httpx
import pytest
import respx

from app.analysis_service import reset_service
from app.config import settings
from app.datasets import parquet_path
from conftest import SALES_CSV, upload

EDGE = "http://r-edge:8090"
TOKEN = "x" * 40
OK = {"status": "complete", "results": {"a": 1}}


@pytest.fixture(autouse=True)
def remote_mode(monkeypatch):
    monkeypatch.setattr(settings, "r_worker_urls", EDGE)
    monkeypatch.setattr(settings, "r_worker_token", TOKEN)
    monkeypatch.setattr(settings, "r_worker_sync_datasets", True)
    reset_service()   # build_service lê a configuração ao montar


async def run(client, ds_id, **opts):
    return await client.post("/analyses/run", json={"analysis": "TTestIndependentSamples", "dataset_id": ds_id, "options": opts})


@respx.mock
async def test_dataset_is_uploaded_once_with_the_token(client):
    ds = await upload(client, SALES_CSV)
    info = respx.get(f"{EDGE}/datasets/{ds['id']}").respond(404)
    put = respx.put(f"{EDGE}/datasets/{ds['id']}").respond(201, json={"size": 1})
    runs = respx.post(f"{EDGE}/run").respond(json=OK)

    assert (await run(client, ds["id"], dependent="receita", group="regiao")).status_code == 200
    assert put.call_count == 1
    sent = put.calls.last.request
    assert sent.content == parquet_path(ds["id"]).read_bytes()          # o Parquet inteiro, byte a byte
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    assert runs.calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"

    assert (await run(client, ds["id"], dependent="nota", group="regiao")).status_code == 200   # outra análise, mesmo dataset
    assert info.call_count == 1 and put.call_count == 1                 # não pergunta nem reenvia
    assert runs.call_count == 2


@respx.mock
async def test_skips_upload_when_worker_already_has_the_file(client):
    ds = await upload(client, SALES_CSV)
    size = parquet_path(ds["id"]).stat().st_size
    respx.get(f"{EDGE}/datasets/{ds['id']}").respond(json={"size": size})
    put = respx.put(f"{EDGE}/datasets/{ds['id']}").respond(201)
    respx.post(f"{EDGE}/run").respond(json=OK)
    assert (await run(client, ds["id"])).status_code == 200
    assert not put.called


@respx.mock
async def test_resends_when_the_edge_dropped_the_file(client):
    """O edge limita o cache e pode apagar o Parquet: o worker responde "dataset not found" e a API reenvia."""
    ds = await upload(client, SALES_CSV)
    respx.get(f"{EDGE}/datasets/{ds['id']}").respond(404)
    put = respx.put(f"{EDGE}/datasets/{ds['id']}").respond(201)
    runs = respx.post(f"{EDGE}/run").mock(side_effect=[
        httpx.Response(400, json={"message": f"dataset not found: {ds['id']}"}),
        httpx.Response(200, json=OK),
    ])
    r = await run(client, ds["id"])
    assert r.status_code == 200 and r.json()["results"] == {"a": 1}
    assert put.call_count == 2 and runs.call_count == 2


@respx.mock
async def test_rejected_token_is_explained(client):
    ds = await upload(client, SALES_CSV)
    respx.get(f"{EDGE}/datasets/{ds['id']}").respond(401)
    runs = respx.post(f"{EDGE}/run").respond(json=OK)
    r = await run(client, ds["id"])
    assert r.status_code == 502 and "R_WORKER_TOKEN" in r.text
    assert not runs.called


@respx.mock
async def test_remote_worker_down_is_a_service_error_not_a_crash(client):
    ds = await upload(client, SALES_CSV)
    respx.get(f"{EDGE}/datasets/{ds['id']}").mock(side_effect=httpx.ConnectError("sem rota"))
    r = await run(client, ds["id"])
    assert r.status_code in (502, 503)


@respx.mock
async def test_unknown_dataset_never_reaches_the_edge(client):
    with respx.mock(assert_all_called=False) as m:
        any_call = m.route().respond(json=OK)
        assert (await run(client, "0" * 32)).status_code == 404
        assert not any_call.called


@respx.mock
async def test_local_mode_is_unchanged(client, monkeypatch):
    monkeypatch.setattr(settings, "r_worker_sync_datasets", False)
    monkeypatch.setattr(settings, "r_worker_token", "")
    reset_service()
    ds = await upload(client, SALES_CSV)
    runs = respx.post(f"{EDGE}/run").respond(json=OK)
    assert (await run(client, ds["id"])).status_code == 200
    assert "authorization" not in runs.calls.last.request.headers
    assert respx.calls.call_count == 1   # nada além do /run
