import sqlite3

import pytest
from conftest import SALES_CSV
from test_auth import auth_on, login, make_user, new_client, setup_admin  # noqa: F401

from app.config import settings


async def events(admin, **params):
    r = await admin.get("/audit", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_audit_records_the_important_things(client, auth_on):
    await setup_admin(client)
    u = await make_user(client, "edu", "editor")
    anon = new_client()
    await anon.post("/auth/login", json={"username": "edu", "password": "errada-errada"})
    ed = await login("edu")
    rep = (await ed.post("/reports", json={"title": "Meu relatório", "blocks": []})).json()
    ds = (await ed.post("/datasets", files={"file": ("v.csv", SALES_CSV.encode(), "text/csv")})).json()
    await ed.put(f"/datasets/{ds['id']}/access", json={"restricted": True, "user_ids": [], "rls": None})
    await client.patch(f"/users/{u['id']}", json={"role": "viewer"})
    await ed.delete(f"/reports/{rep['id']}")  # agora é viewer: 403 => "denied"
    await client.delete(f"/reports/{rep['id']}")
    got = await events(client, limit=100)
    pairs = [(e["action"], e["username"], e["kind"]) for e in got]
    for expected in [("setup", "ana", "user"), ("create_user", "ana", "user"), ("login_failed", "edu", "user"), ("login", "edu", "user"),
                     ("create", "edu", "report"), ("create", "edu", "dataset"), ("set_access", "edu", "dataset"), ("update_user", "ana", "user"),
                     ("denied", "edu", None), ("delete", "ana", "report")]:
        assert expected in pairs, expected
    assert [e["id"] for e in got] == sorted((e["id"] for e in got), reverse=True)  # mais recente primeiro
    assert next(e for e in got if e["action"] == "create" and e["kind"] == "report")["detail"] == "Meu relatório"
    assert next(e for e in got if e["action"] == "update_user")["detail"].endswith("→ viewer")
    assert "senha-forte" not in str(got) and "errada-errada" not in str(got)  # nunca registra senhas


async def test_audit_is_admin_only_and_paginates_and_filters(client, auth_on):
    await setup_admin(client)
    await make_user(client, "edu", "editor")
    ed = await login("edu")
    assert (await ed.get("/audit")).status_code == 403
    assert (await new_client().get("/audit")).status_code == 401
    for i in range(5):
        await ed.post("/collections", json={"name": f"c{i}"})
    first = await events(client, limit=3)
    assert len(first) == 3
    nxt = await events(client, limit=3, before_id=first[-1]["id"])
    assert nxt and nxt[0]["id"] < first[-1]["id"]
    only = await events(client, action="create", limit=50)
    assert only and all(e["action"] == "create" for e in only)


async def test_login_lock_is_audited_without_user(client, auth_on, monkeypatch):
    await setup_admin(client)
    monkeypatch.setattr(settings, "login_max_failures", 2)
    anon = new_client()
    for _ in range(3):
        await anon.post("/auth/login", json={"username": "ana", "password": "x" * 9})
    actions = [e["action"] for e in await events(client)]
    assert actions.count("login_failed") == 2 and "login_locked" in actions


async def test_audit_failure_does_not_break_the_operation(client, auth_on, monkeypatch):
    from app import audit, db
    await setup_admin(client)
    monkeypatch.setattr(audit.db, "connect", lambda: (_ for _ in ()).throw(RuntimeError("disco cheio")))
    audit.log(None, "x")  # não propaga


# ---------- expiração por inatividade ----------

def _age_session(hours: float) -> None:
    import datetime
    old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
    con = sqlite3.connect(settings.data_dir / "meta.db")
    con.execute("UPDATE sessions SET last_seen = ?", [old])
    con.commit()


async def test_idle_session_expires(client, auth_on, monkeypatch):
    await setup_admin(client)
    monkeypatch.setattr(settings, "session_idle_hours", 12.0)
    assert (await client.get("/datasets")).status_code == 200
    _age_session(13)
    assert (await client.get("/datasets")).status_code == 401  # parada por mais de 12 h


async def test_activity_keeps_session_alive_and_idle_can_be_disabled(client, auth_on, monkeypatch):
    await setup_admin(client)
    monkeypatch.setattr(settings, "session_idle_hours", 12.0)
    _age_session(11)  # quase vencendo
    assert (await client.get("/datasets")).status_code == 200  # usar renova a última atividade
    con = sqlite3.connect(settings.data_dir / "meta.db")
    import datetime
    seen = datetime.datetime.fromisoformat(con.execute("SELECT last_seen FROM sessions").fetchone()[0])
    assert datetime.datetime.now(datetime.timezone.utc) - seen < datetime.timedelta(minutes=5)
    _age_session(500)
    monkeypatch.setattr(settings, "session_idle_hours", 0)
    assert (await client.get("/datasets")).status_code == 200  # 0 desliga


async def test_auth_disabled_still_audits_without_user(client):
    r = await client.post("/reports", json={"title": "sem login", "blocks": []})
    assert r.status_code == 201
    got = (await client.get("/audit")).json()  # "admin" anônimo lê
    e = next(e for e in got if e["action"] == "create")
    assert e["user_id"] is None and e["detail"] == "sem login"
