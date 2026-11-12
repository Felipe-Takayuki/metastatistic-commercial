import pytest

from auth_tenant_service.audit_client import AuditClient


@pytest.fixture(autouse=True)
def recorded_audit_events(monkeypatch):
    """Evita chamadas HTTP reais ao audit-service e expõe os eventos que seriam enviados."""
    events = []
    monkeypatch.setattr(AuditClient, "record_event", lambda self, event: events.append(event))
    return events
