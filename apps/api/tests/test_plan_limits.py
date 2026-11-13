"""Limites do plano Free/Pro aplicados na API (cabeçalhos X-Tenant-* vêm do gateway)."""
import json

import httpx
import pytest

from app import audit, db
from app.config import settings
from app.main import app

from conftest import SALES_CSV

FREE = {"X-Tenant-ID": "org-free", "X-Tenant-Tier": "community",
        "X-Tenant-Quotas": json.dumps({"max_datasets": 2, "max_upload_mb": 1})}
PRO = {"X-Tenant-ID": "org-pro", "X-Tenant-Tier": "team",
       "X-Tenant-Quotas": json.dumps({"max_datasets": 4, "max_upload_mb": 5})}


@pytest.fixture
async def admin(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/auth/setup", json={"username": "ana", "password": "senha-forte-1", "display_name": "Ana"})
        assert r.status_code == 201, r.text
        yield c


def csv(name="a.csv", text=SALES_CSV):
    return {"file": (name, text.encode(), "text/csv")}


async def test_free_plan_blocks_the_dataset_over_the_limit_with_a_helpful_message(admin):
    for i in range(2):
        assert (await admin.post("/datasets", files=csv(f"d{i}.csv"), headers=FREE)).status_code == 201

    r = await admin.post("/datasets", files=csv("d3.csv"), headers=FREE)
    assert r.status_code == 402
    msg = r.json()["detail"]
    assert "plano Free" in msg and "2 datasets" in msg      # diz o limite
    assert "Pro" in msg                                     # diz como liberar
    assert len((await admin.get("/datasets", headers=FREE)).json()) == 2   # nada foi criado


async def test_limit_is_per_organization_and_pro_has_more_room(admin):
    for i in range(2):
        await admin.post("/datasets", files=csv(f"f{i}.csv"), headers=FREE)
    assert (await admin.post("/datasets", files=csv("f3.csv"), headers=FREE)).status_code == 402
    # outra organização, no Pro, tem a própria conta e o limite maior
    for i in range(4):
        assert (await admin.post("/datasets", files=csv(f"p{i}.csv"), headers=PRO)).status_code == 201
    r = await admin.post("/datasets", files=csv("p5.csv"), headers=PRO)
    assert r.status_code == 402 and "plano Pro" in r.json()["detail"] and "4 datasets" in r.json()["detail"]


async def test_upgrade_frees_room_immediately(admin):
    for i in range(2):
        await admin.post("/datasets", files=csv(f"u{i}.csv"), headers=FREE)
    assert (await admin.post("/datasets", files=csv("u3.csv"), headers=FREE)).status_code == 402
    upgraded = {**FREE, "X-Tenant-Tier": "team", "X-Tenant-Quotas": json.dumps({"max_datasets": 100, "max_upload_mb": 200})}
    assert (await admin.post("/datasets", files=csv("u3.csv"), headers=upgraded)).status_code == 201


async def test_file_size_limit_of_the_plan(admin):
    big = "id,v\n" + "\n".join(f"{i},{i * 3}" for i in range(250_000))   # > 1 MB
    assert len(big) > 1024 * 1024
    r = await admin.post("/datasets", files=csv("big.csv", big), headers=FREE)
    assert r.status_code == 402
    assert "plano Free" in r.json()["detail"] and "1 MB" in r.json()["detail"]
    assert (await admin.post("/datasets", files=csv("big.csv", big), headers=PRO)).status_code == 201


async def test_without_gateway_headers_the_free_limits_apply(admin):
    for i in range(5):
        assert (await admin.post("/datasets", files=csv(f"s{i}.csv"))).status_code == 201
    r = await admin.post("/datasets", files=csv("s6.csv"))
    assert r.status_code == 402 and "5 datasets" in r.json()["detail"]


async def test_garbled_quota_header_falls_back_to_free(admin):
    h = {"X-Tenant-ID": "org-x", "X-Tenant-Tier": "team", "X-Tenant-Quotas": "{not json"}
    for i in range(5):
        await admin.post("/datasets", files=csv(f"g{i}.csv"), headers=h)
    assert (await admin.post("/datasets", files=csv("g6.csv"), headers=h)).status_code == 402


async def test_datasets_saved_from_queries_count_too(admin):
    for i in range(2):
        await admin.post("/datasets", files=csv(f"q{i}.csv"), headers=FREE)
    r = await admin.post("/datasets/from-query", json={"name": "derivado", "sql": "SELECT 1 AS x"}, headers=FREE)
    assert r.status_code == 402


async def test_auth_disabled_means_no_limits(client):
    for i in range(7):
        assert (await client.post("/datasets", files=csv(f"n{i}.csv"))).status_code == 201


async def test_plan_is_recorded_in_the_audit_trail(admin):
    await admin.post("/datasets", files=csv("aud.csv"), headers=FREE)
    events = audit.list_events(action="create")
    assert any("upload" in (e["detail"] or "") and "plano Free" in (e["detail"] or "") for e in events)


async def test_business_events_are_written_to_the_process_log(admin):
    import logging

    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    audit.events_log.addHandler(handler)
    try:
        await admin.post("/datasets", files=csv("log.csv"), headers=FREE)
    finally:
        audit.events_log.removeHandler(handler)
    ev = next(json.loads(r) for r in records if json.loads(r)["event"] == "dataset.create")
    assert ev["user"] == "ana" and "plano Free" in ev["detail"]


# ---------- cada usuário vê só os próprios dados (dataset privado por padrão) ----------

async def test_new_datasets_are_private_to_their_owner_when_configured(admin, monkeypatch):
    from conftest import SALES_CSV as _csv  # noqa: F401
    from test_auth import login, make_user

    monkeypatch.setattr(settings, "datasets_private_by_default", True)
    await make_user(admin, "ed1", "editor")
    await make_user(admin, "ed2", "editor")
    ed1, ed2 = await login("ed1"), await login("ed2")

    mine = (await ed1.post("/datasets", files=csv("meu.csv"))).json()
    assert mine["restricted"] is True

    assert [d["id"] for d in (await ed1.get("/datasets")).json()] == [mine["id"]]     # o dono vê
    assert (await ed2.get("/datasets")).json() == []                                   # outro usuário não vê
    assert (await ed2.get(f"/datasets/{mine['id']}")).status_code == 404               # nem confirma que existe
    assert len((await admin.get("/datasets")).json()) == 1                              # administrador vê

    # o dono decide compartilhar
    ed2_id = (await ed2.get("/auth/me")).json()["id"]
    r = await ed1.put(f"/datasets/{mine['id']}/access", json={"restricted": True, "user_ids": [ed2_id], "rls": None})
    assert r.status_code == 200
    assert len((await ed2.get("/datasets")).json()) == 1


async def test_datasets_stay_open_by_default_for_backward_compatibility(admin):
    from test_auth import login, make_user

    await make_user(admin, "ed3", "editor")
    ed3 = await login("ed3")
    await admin.post("/datasets", files=csv("aberto.csv"))
    assert len((await ed3.get("/datasets")).json()) == 1
