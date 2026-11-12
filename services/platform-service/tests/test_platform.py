import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from platform_service.main import MOUNTS, app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # `with` dispara o lifespan (inicializa os bancos de auth e bi)
        yield c


def test_every_mount_answers_health(client):
    assert client.get("/health").json()["status"] == "healthy"
    for prefix in MOUNTS:
        r = client.get(f"{prefix}/health")
        assert r.status_code == 200, (prefix, r.text)


def test_paths_inside_a_service_are_the_original_ones(client):
    created = client.post("/_auth/tenants", json={"name": "Lab", "tier": "team", "owner_id": "u1", "owner_email": "a@b.co"})
    assert created.status_code == 201, created.text
    tenant = created.json()
    assert client.get(f"/_auth/tenants/{tenant['id']}/access/u1").json()["role"] == "owner"
    assert client.get(f"/_auth/tenants/{tenant['id']}/access/ninguem").status_code == 404
    assert client.get("/_billing/billing/plans").status_code == 200


def test_services_keep_separate_databases(client):
    paths = {n: os.environ[f"{n}_DATABASE_URL"].removeprefix("sqlite:///") for n in ("AUDIT", "AUTH", "BILLING", "BI")}
    assert len(set(paths.values())) == 4
    for name in ("AUTH", "BI"):   # criados pelo lifespan dos apps montados
        assert os.path.exists(paths[name]), name
        assert sqlite3.connect(paths[name]).execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0


def test_unknown_prefix_is_404(client):
    assert client.get("/_nada/health").status_code == 404
