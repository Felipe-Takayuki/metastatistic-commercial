import httpx
import respx

from auth_tenant_service.audit_client import AuditClient, AuditEventCreate
from auth_tenant_service.main import app, get_store
from auth_tenant_service.tenants import TenantStore
from fastapi.testclient import TestClient

# Capturado na importação do módulo, antes de o conftest trocar o método por um fake.
REAL_RECORD_EVENT = AuditClient.record_event


def send(base_url: str, event: AuditEventCreate) -> None:
    REAL_RECORD_EVENT(AuditClient(base_url), event)


EVENT = AuditEventCreate(tenant_id="t1", user_id="u1", action="tenant.create", resource_type="tenant", details={"a": 1})


@respx.mock
def test_record_event_posts_to_audit_service():
    route = respx.post("http://audit.test/audit/events").mock(return_value=httpx.Response(201, json={}))
    send("http://audit.test/", EVENT)

    assert route.called
    body = route.calls.last.request.read()
    assert b'"action":"tenant.create"' in body.replace(b" ", b"")


@respx.mock
def test_record_event_swallows_connection_errors(caplog):
    respx.post("http://audit.test/audit/events").mock(side_effect=httpx.ConnectError("down"))
    send("http://audit.test", EVENT)  # não levanta
    assert "Failed to record audit event tenant.create" in caplog.text


@respx.mock
def test_record_event_swallows_http_errors():
    respx.post("http://audit.test/audit/events").mock(return_value=httpx.Response(500))
    send("http://audit.test", EVENT)  # não levanta


def test_record_event_disabled_when_url_empty():
    with respx.mock:  # qualquer chamada HTTP falharia (rota não mockada)
        send("", EVENT)


def test_create_tenant_emits_audit_event(tmp_path, recorded_audit_events):
    store = TenantStore(str(tmp_path / "t.db"))
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/tenants",
                json={"name": "Acme", "tier": "team", "owner_id": "o1", "owner_email": "o@acme.io"},
            )
            assert resp.status_code == 201
    finally:
        app.dependency_overrides.clear()

    assert [e.action for e in recorded_audit_events] == ["tenant.create"]
    assert recorded_audit_events[0].tenant_id == resp.json()["id"]
