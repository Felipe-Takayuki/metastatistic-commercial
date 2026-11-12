import json
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from edge.main import create_app

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ID1, ID2, ID3 = "a" * 32, "b" * 32, "c" * 32
PARQUET = b"PAR1" + b"\x00" * 64 + b"PAR1"


class Worker:
    """R worker de mentira atrás de um MockTransport."""

    def __init__(self):
        self.calls: list[tuple[str, str, bytes]] = []
        self.mode = "ok"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path, request.content))
        if self.mode == "down":
            raise httpx.ConnectError("refused")
        if self.mode == "slow":
            raise httpx.ReadTimeout("slow")
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "engine": "r"})
        return httpx.Response(200, json={"status": "complete", "results": {"x": 1}})


@pytest.fixture
def worker():
    return Worker()


@pytest.fixture
def make(tmp_path, worker):
    def build(**kw):
        client = httpx.AsyncClient(transport=httpx.MockTransport(worker))
        app = create_app(token=TOKEN, data_dir=tmp_path, worker_url="http://r-worker:8000", client=client, **kw)
        return TestClient(app)
    return build


def test_token_is_required_and_must_be_long(make):
    c = make()
    assert c.get("/live").status_code == 200   # só o liveness é público
    for path in ("/health", f"/datasets/{ID1}"):
        assert c.get(path).status_code == 401
        assert c.get(path, headers={"Authorization": "Bearer errado"}).status_code == 401
        assert c.get(path, headers={"Authorization": TOKEN}).status_code == 401   # sem o esquema Bearer
    assert c.post("/run", json={}).status_code == 401
    assert c.put(f"/datasets/{ID1}", content=PARQUET).status_code == 401
    with pytest.raises(ValueError, match="pelo menos 32"):
        create_app(token="curto", data_dir="/tmp/x", worker_url="http://w")


def test_upload_roundtrip_and_atomic_file(make, tmp_path):
    c = make()
    assert c.get(f"/datasets/{ID1}", headers=AUTH).status_code == 404
    r = c.put(f"/datasets/{ID1}", content=PARQUET, headers=AUTH)
    assert r.status_code == 201 and r.json() == {"size": len(PARQUET)}
    assert c.get(f"/datasets/{ID1}", headers=AUTH).json() == {"size": len(PARQUET)}
    assert (tmp_path / "datasets" / f"{ID1}.parquet").read_bytes() == PARQUET   # onde o worker R lê
    assert not list((tmp_path / "datasets").glob("*.part"))                      # sem sobras
    assert c.delete(f"/datasets/{ID1}", headers=AUTH).status_code == 204
    assert c.get(f"/datasets/{ID1}", headers=AUTH).status_code == 404


@pytest.mark.parametrize("bad", ["../etc/passwd", "AAAA", "a" * 31, "a" * 33, "g" * 32, "a" * 32 + ".parquet"])
def test_dataset_id_must_be_32_hex(make, bad):
    c = make()
    r = c.put(f"/datasets/{bad}", content=PARQUET, headers=AUTH)
    assert r.status_code in (400, 404, 405)   # nunca grava fora de datasets/


def test_rejects_non_parquet_and_oversize(make, tmp_path):
    c = make(max_upload_bytes=1000)
    assert c.put(f"/datasets/{ID1}", content=b"a,b\n1,2\n", headers=AUTH).status_code == 422
    assert c.put(f"/datasets/{ID1}", content=b"PAR1" + b"\x00" * 64, headers=AUTH).status_code == 422   # sem o PAR1 final
    assert c.put(f"/datasets/{ID1}", content=b"PAR1" + b"\x00" * 2000 + b"PAR1", headers=AUTH).status_code == 413
    assert not list((tmp_path / "datasets").iterdir())   # nada ficou gravado


def test_cache_evicts_least_recently_used(make, tmp_path):
    c = make(max_cache_bytes=len(PARQUET) * 2 + 10)
    for i, ds in enumerate((ID1, ID2)):
        c.put(f"/datasets/{ds}", content=PARQUET, headers=AUTH)
        os.utime(tmp_path / "datasets" / f"{ds}.parquet", (time.time() - 100 + i, time.time() - 100 + i))
    c.post("/run", json={"dataset_id": ID1}, headers=AUTH)   # usar o ID1 o torna o mais recente
    c.put(f"/datasets/{ID3}", content=PARQUET, headers=AUTH)   # estoura o limite: sai o ID2, o menos usado
    left = {p.stem for p in (tmp_path / "datasets").glob("*.parquet")}
    assert left == {ID1, ID3}


def test_run_and_health_are_proxied(make, worker):
    c = make()
    body = {"analysis": "ttest", "dataset_id": ID1, "timeout_s": 5}
    r = c.post("/run", json=body, headers=AUTH)
    assert r.status_code == 200 and r.json()["results"] == {"x": 1}
    method, path, sent = worker.calls[-1]
    assert (method, path) == ("POST", "/run") and json.loads(sent) == body   # o corpo chega intacto
    h = c.get("/health", headers=AUTH)
    assert h.status_code == 200 and h.json()["engine"] == "r"


def test_worker_down_and_timeout_map_to_503_and_504(make, worker):
    c = make()
    worker.mode = "down"
    r = c.post("/run", json={"dataset_id": ID1}, headers=AUTH)
    assert r.status_code == 503 and r.json()["code"] == "worker_unavailable"
    assert c.get("/health", headers=AUTH).status_code == 503
    worker.mode = "slow"
    r = c.post("/run", json={}, headers=AUTH)
    assert r.status_code == 504 and r.json()["code"] == "timeout"   # o mesmo `code` que os clientes já tratam


def test_run_with_garbage_body_still_reaches_the_worker(make, worker):
    c = make()
    assert c.post("/run", content=b"nao e json", headers=AUTH).status_code == 200
    assert worker.calls[-1][2] == b"nao e json"
