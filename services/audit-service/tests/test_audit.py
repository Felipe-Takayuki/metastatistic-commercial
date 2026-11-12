import sqlite3

import pytest
from fastapi.testclient import TestClient

from audit_service.audit_trail import GENESIS_HASH, AuditTrailManager
from audit_service.db import AuditDatabase
from audit_service.import_legacy import import_legacy
from audit_service.main import app, get_audit_manager


@pytest.fixture
def db(tmp_path):
    return AuditDatabase(str(tmp_path / "audit_test.db"))


@pytest.fixture
def client(db):
    manager = AuditTrailManager(db.get_connection)
    app.dependency_overrides[get_audit_manager] = lambda: manager
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def post_event(client, tenant_id="t1", action="dataset.upload", **extra):
    resp = client.post(
        "/audit/events",
        json={"tenant_id": tenant_id, "user_id": "investigator_01", "action": action,
              "resource_type": "dataset", **extra},
    )
    assert resp.status_code == 201
    return resp.json()


def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "healthy"
    assert data["service"] == "audit-service"


def test_hash_chain_links_events_per_tenant(client):
    first = post_event(client, "t1")
    second = post_event(client, "t1")
    other_tenant = post_event(client, "t2")

    assert first["prev_hash"] == GENESIS_HASH
    assert second["prev_hash"] == first["record_hash"]
    assert other_tenant["prev_hash"] == GENESIS_HASH  # cadeia independente por tenant


def test_list_events_filters(client):
    post_event(client, "t1", action="auth.login")
    post_event(client, "t1", action="dataset.upload")
    post_event(client, "t2", action="auth.login")

    assert len(client.get("/audit/events").json()) == 3
    assert len(client.get("/audit/events?tenant_id=t1").json()) == 2
    logins = client.get("/audit/events?action=auth.login").json()
    assert {e["tenant_id"] for e in logins} == {"t1", "t2"}
    assert len(client.get("/audit/events?limit=1").json()) == 1


def test_verify_and_export(client):
    for action in ("auth.login", "dataset.upload", "analysis.anova", "report.export"):
        post_event(client, "t1", action=action, details={"k": action})

    verify = client.get("/audit/verify?tenant_id=t1").json()
    assert verify["valid"] is True
    assert verify["total_records"] == 4
    assert verify["latest_hash"] is not None

    export = client.get("/audit/export?tenant_id=t1").json()
    assert export["compliance_standard"] == "SOC 2 Type II / FDA 21 CFR Part 11"
    assert export["integrity_verified"] is True
    assert [e["action"] for e in export["events"]] == ["auth.login", "dataset.upload", "analysis.anova", "report.export"]


def test_verify_empty_trail_is_valid(client):
    data = client.get("/audit/verify?tenant_id=nobody").json()
    assert data["valid"] is True
    assert data["total_records"] == 0


def test_tamper_detection(client, db):
    events = [post_event(client, "t1", details={"records": i}) for i in range(4)]
    target = events[1]

    with db.get_connection() as conn:
        conn.execute("UPDATE audit_log SET details = ? WHERE id = ?", ('{"records": 99999999}', target["id"]))
        conn.commit()

    data = client.get("/audit/verify?tenant_id=t1").json()
    assert data["valid"] is False
    assert data["tampered_at_id"] == target["id"]
    assert data["tampered_event_id"] == target["event_id"]
    assert "Content tampering detected" in data["reason"]
    assert client.get("/audit/export?tenant_id=t1").json()["integrity_verified"] is False


def test_tamper_detection_broken_chain(client, db):
    events = [post_event(client, "t1") for _ in range(3)]

    with db.get_connection() as conn:
        conn.execute("DELETE FROM audit_log WHERE id = ?", (events[1]["id"],))
        conn.commit()

    data = client.get("/audit/verify?tenant_id=t1").json()
    assert data["valid"] is False
    assert data["tampered_at_id"] == events[2]["id"]
    assert "Broken hash chain" in data["reason"]


def test_global_verify_with_multiple_tenants(client):
    # Eventos intercalados: a cadeia é por tenant, então a verificação global não pode exigir uma cadeia única.
    for tenant in ("t1", "t2", "t1", "t3", "t2", "t1"):
        post_event(client, tenant)

    data = client.get("/audit/verify").json()
    assert data["valid"] is True
    assert data["total_records"] == 6
    assert data["latest_hash"] == client.get("/audit/events?limit=1").json()[0]["record_hash"]
    assert client.get("/audit/export").json()["integrity_verified"] is True


def test_global_verify_detects_tampering_in_any_tenant(client, db):
    events = [post_event(client, tenant) for tenant in ("t1", "t2", "t1", "t2")]
    target = events[3]  # último evento do t2

    with db.get_connection() as conn:
        conn.execute("UPDATE audit_log SET details = ? WHERE id = ?", ('{"x": 1}', target["id"]))
        conn.commit()

    data = client.get("/audit/verify").json()
    assert data["valid"] is False
    assert data["tampered_at_id"] == target["id"]
    assert data["total_records"] == 4
    # as cadeias dos tenants íntegros continuam válidas
    assert client.get("/audit/verify?tenant_id=t1").json()["valid"] is True
    assert client.get("/audit/verify?tenant_id=t2").json()["valid"] is False


def test_import_legacy_preserves_chain_and_is_idempotent(client, tmp_path):
    # Simula o auth_tenant.db antigo: mesma tabela audit_log, populada pelo gerenciador original
    legacy = AuditDatabase(str(tmp_path / "auth_tenant.db"))
    legacy_manager = AuditTrailManager(legacy.get_connection)
    from audit_service.audit_trail import AuditEventCreate
    for i in range(3):
        legacy_manager.record_event(
            AuditEventCreate(tenant_id="t1", user_id="u", action="legacy.event", resource_type="x", details={"i": i})
        )

    target_url = f"sqlite:///{tmp_path / 'new_audit.db'}"
    assert import_legacy(legacy.db_path, target_url) == 3
    assert import_legacy(legacy.db_path, target_url) == 0  # idempotente

    imported = AuditTrailManager(AuditDatabase(target_url).get_connection)
    assert imported.verify_integrity("t1").valid is True
    assert imported.verify_integrity("t1").total_records == 3

    # Novos eventos continuam a cadeia herdada
    last_legacy_hash = imported.list_events(tenant_id="t1", limit=1)[0].record_hash
    new_event = imported.record_event(
        AuditEventCreate(tenant_id="t1", user_id="u", action="new.event", resource_type="x")
    )
    assert new_event.prev_hash == last_legacy_hash
    assert imported.verify_integrity("t1").valid is True

    # A tabela original não foi alterada
    with sqlite3.connect(legacy.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 3
