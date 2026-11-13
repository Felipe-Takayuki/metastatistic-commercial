"""Uma organização nunca lista, abre, consulta por SQL, edita nem apaga o que é de outra (X-Tenant-ID vem do gateway)."""
import json

import httpx
import pytest

from app.config import settings
from app.main import app

from conftest import SALES_CSV

A = {"X-Tenant-ID": "org-a", "X-Tenant-Tier": "team", "X-Tenant-Quotas": json.dumps({"max_datasets": 50, "max_upload_mb": 50})}
B = {**A, "X-Tenant-ID": "org-b"}


@pytest.fixture
async def admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/auth/setup", json={"username": "ana", "password": "senha-forte-1", "display_name": "Ana"})
        assert r.status_code == 201, r.text
        yield c


def csv(name="v.csv"):
    return {"file": (name, SALES_CSV.encode(), "text/csv")}


async def test_datasets_are_invisible_across_organizations(admin):
    ds = (await admin.post("/datasets", files=csv(), headers=A)).json()
    assert [d["id"] for d in (await admin.get("/datasets", headers=A)).json()] == [ds["id"]]
    assert (await admin.get("/datasets", headers=B)).json() == []                       # nem o administrador da plataforma cruza
    assert (await admin.get(f"/datasets/{ds['id']}", headers=B)).status_code == 404
    assert (await admin.get(f"/datasets/{ds['id']}/preview", headers=B)).status_code == 404
    assert (await admin.delete(f"/datasets/{ds['id']}", headers=B)).status_code == 404
    assert (await admin.get(f"/datasets/{ds['id']}", headers=A)).status_code == 200      # continua lá


async def test_sql_only_sees_the_organization_datasets(admin):
    ds = (await admin.post("/datasets", files=csv(), headers=A)).json()
    sql = {"sql": f'SELECT count(*) AS n FROM "{ds["table_name"]}"'}
    ok = await admin.post("/queries/run", json=sql, headers=A)
    assert ok.status_code == 200 and ok.json()["rows"][0][0] == 4
    other = await admin.post("/queries/run", json=sql, headers=B)       # a tabela simplesmente não existe para a outra organização
    assert other.status_code == 422 and "does not exist" in other.text


async def test_same_dataset_name_in_two_organizations_does_not_collide(admin):
    a = (await admin.post("/datasets", files=csv("vendas.csv"), headers=A)).json()
    b = (await admin.post("/datasets", files=csv("vendas.csv"), headers=B)).json()
    assert a["id"] != b["id"]
    assert len((await admin.get("/datasets", headers=A)).json()) == 1
    assert len((await admin.get("/datasets", headers=B)).json()) == 1


async def test_reports_dashboards_and_collections_are_per_organization(admin):
    rep = (await admin.post("/reports", json={"title": "Meu", "blocks": []}, headers=A)).json()
    dash = (await admin.post("/dashboards", json={"title": "Painel", "tiles": [], "filters": []}, headers=A)).json()
    col = (await admin.post("/collections", json={"name": "Estudo 1"}, headers=A)).json()

    assert (await admin.get("/reports", headers=B)).json() == []
    assert (await admin.get("/dashboards", headers=B)).json() == []
    assert (await admin.get("/collections", headers=B)).json() == []
    assert (await admin.get(f"/reports/{rep['id']}", headers=B)).status_code == 404
    assert (await admin.get(f"/dashboards/{dash['id']}", headers=B)).status_code == 404

    # editar/apagar o que é da outra organização também não funciona
    upd = await admin.put(f"/reports/{rep['id']}", json={"title": "Invadido", "blocks": [], "version": rep["version"]}, headers=B)
    assert upd.status_code == 404
    assert (await admin.delete(f"/reports/{rep['id']}", headers=B)).status_code == 404
    assert (await admin.delete(f"/dashboards/{dash['id']}", headers=B)).status_code == 404
    assert (await admin.delete(f"/collections/{col['id']}", headers=B)).status_code == 404
    assert (await admin.get(f"/reports/{rep['id']}", headers=A)).json()["title"] == "Meu"


async def test_workspace_default_is_its_own_isolated_space(admin):
    await admin.post("/datasets", files=csv("legado.csv"))                               # sem cabeçalho = default
    assert len((await admin.get("/datasets")).json()) == 1
    assert (await admin.get("/datasets", headers=A)).json() == []


async def test_no_isolation_when_auth_is_disabled(client):
    await client.post("/datasets", files=csv(), headers=A)
    assert len((await client.get("/datasets", headers=B)).json()) == 1                    # demonstração local: tudo junto


async def test_correlation_id_is_in_the_business_event_log(admin):
    import logging
    from app import audit

    records: list[str] = []

    class Cap(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    h = Cap()
    audit.events_log.addHandler(h)
    try:
        await admin.post("/datasets", files=csv("c.csv"), headers={**A, "X-Correlation-ID": "corr-xyz-789"})
    finally:
        audit.events_log.removeHandler(h)
    ev = next(json.loads(r) for r in records if json.loads(r)["event"] == "dataset.create")
    assert ev["correlation_id"] == "corr-xyz-789" and ev["tenant"] == "org-a"
