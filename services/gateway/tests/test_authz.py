"""Autenticação/autorização no gateway: sessão do apps/api + associação ao tenant (auth-tenant-service)."""
import base64
import json

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app import authz
from app.authz import Access, canonical_path, classify, safe_path
from app.config import settings
from app.main import app

ALICE = {"id": "u_alice", "username": "alice", "role": "editor"}
ADMIN = {"id": "u_root", "username": "root", "role": "admin"}
TENANT_A = "3b1f0000-0000-0000-0000-00000000000a"
TENANT_B = "3b1f0000-0000-0000-0000-00000000000b"
COOKIE = {"Cookie": "ms_session=abc123"}


@pytest.fixture(autouse=True)
def authz_on(monkeypatch):
    monkeypatch.setattr(settings, "authz_enabled", True)
    monkeypatch.setattr(settings, "authz_cache_ttl_s", 0.0)
    authz.clear_cache()


def mock_session(mock, identity=ALICE):
    return mock.get(f"{settings.data_api_url}/auth/me").mock(return_value=httpx.Response(200, json=identity))


def mock_membership(mock, tenant, user, role, slug="lab"):
    return mock.get(f"{settings.auth_service_url}/tenants/{tenant}/access/{user}").mock(
        return_value=httpx.Response(200, json={"tenant_id": tenant, "tenant_slug": slug, "tier": "team", "role": role})
    )


def mock_not_member(mock, tenant, user):
    return mock.get(f"{settings.auth_service_url}/tenants/{tenant}/access/{user}").mock(return_value=httpx.Response(404))


def gateway():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")


# ---------------------------------------------------------------------------
# Política (funções puras)
# ---------------------------------------------------------------------------

def test_canonical_path_aliases():
    assert canonical_path("/api/v1/billing/plans") == "/billing/plans"
    assert canonical_path("/api/billing/plans") == "/billing/plans"
    assert canonical_path("/billing/plans") == "/billing/plans"
    assert canonical_path("/api/v1/sso/saml/acs") == "/auth/sso/saml/acs"


@pytest.mark.parametrize("path", ["/api/v1/../tenants/x/tier", "/api/v1/a/./b", "/api/v1//tenants", "/api/v1/a%2f..%2fb", "/a\\b"])
def test_unsafe_paths_are_rejected(path):
    assert not safe_path(path)


@pytest.mark.parametrize("method,path,service,expected", [
    ("PATCH", "/tenants/t1/tier", "auth", Access.DENY),
    ("GET", "/tenants/t1/access/u1", "auth", Access.DENY),
    ("POST", "/auth/token", "auth", Access.DENY),
    ("POST", "/audit/events", "audit", Access.DENY),
    ("DELETE", "/audit/events", "audit", Access.DENY),
    ("GET", "/audit/events", "audit", Access.ADMIN),
    ("GET", "/auth/status", "data_api", Access.PUBLIC),
    ("POST", "/auth/login", "data_api", Access.PUBLIC),
    ("POST", "/billing/webhook", "billing", Access.PUBLIC),
    ("POST", "/auth/sso/saml/acs", "auth", Access.PUBLIC),
    ("GET", "/anything", "web", Access.PUBLIC),
    ("OPTIONS", "/billing/plans", "billing", Access.PUBLIC),
    ("GET", "/datasets", "data_api", Access.SESSION),
    ("GET", "/auth/me", "data_api", Access.SESSION),
    ("POST", "/tenants", "auth", Access.SESSION),
    ("POST", "/tenants/invitations/tok/accept", "auth", Access.SESSION),
    ("GET", "/tenants/t1", "auth", Access.MEMBER),
    ("GET", "/tenants/t1/members", "auth", Access.MEMBER),
    ("PATCH", "/tenants/t1/members/u2", "auth", Access.ADMIN),
    ("POST", "/tenants/t1/invitations", "auth", Access.ADMIN),
    ("POST", "/tenants/t1/sso/config", "auth", Access.ADMIN),
    ("GET", "/scim/v2/tenants/t1/Users", "auth", Access.ADMIN),
    ("POST", "/billing/checkout", "billing", Access.ADMIN),
    ("GET", "/billing/subscription", "billing", Access.MEMBER),
    ("GET", "/reports", "bi_report", Access.MEMBER),
    ("POST", "/analyses/run", "stat", Access.MEMBER),
    ("POST", "/export/pdf", "export", Access.MEMBER),
    ("POST", "/queries/run", "data_engine", Access.MEMBER),
    ("GET", "/qualquer-coisa-nova", "unknown", Access.MEMBER),  # padrão fechado
])
def test_classification(method, path, service, expected):
    assert classify(method, path, service).access is expected


# ---------------------------------------------------------------------------
# O ataque original: sem credencial, X-Tenant-ID alheio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_session_is_rejected_even_with_tenant_header():
    with respx.mock(assert_all_called=False) as mock:
        billing = mock.get(f"{settings.billing_service_url}/billing/subscription").mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/subscription", headers={"X-Tenant-ID": TENANT_A})
    assert resp.status_code == 401
    assert not billing.called


@pytest.mark.asyncio
async def test_forged_unsigned_jwt_is_rejected():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    forged = f"{b64({'alg': 'HS256'})}.{b64({'tenant_id': TENANT_A, 'role': 'owner'})}.assinatura-invalida"
    with respx.mock(assert_all_called=False) as mock:
        billing = mock.get(f"{settings.billing_service_url}/billing/invoices").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/invoices", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
    assert not billing.called


@pytest.mark.asyncio
async def test_invalid_session_cookie_is_rejected():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{settings.data_api_url}/auth/me").mock(return_value=httpx.Response(401, json={"detail": "authentication required"}))
        billing = mock.get(f"{settings.billing_service_url}/billing/subscription").mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/subscription", headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert resp.status_code == 401 and not billing.called


@pytest.mark.asyncio
async def test_authenticated_non_member_cannot_read_other_tenant():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_not_member(mock, TENANT_B, "u_alice")
        billing = mock.get(f"{settings.billing_service_url}/billing/subscription").mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/subscription", headers={**COOKIE, "X-Tenant-ID": TENANT_B})
    assert resp.status_code == 403
    assert not billing.called


@pytest.mark.asyncio
async def test_member_is_allowed_and_downstream_gets_only_verified_identity():
    with respx.mock(assert_all_called=True) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "analyst", slug="acme")
        billing = mock.get(f"{settings.billing_service_url}/billing/subscription").mock(return_value=httpx.Response(200, json={"ok": 1}))
        async with gateway() as client:
            resp = await client.get(
                "/api/v1/billing/subscription",
                headers={**COOKIE, "X-Tenant-ID": TENANT_A, "X-User-ID": "u_root", "X-User-Role": "admin", "X-Tenant-Role": "owner"},
            )
    assert resp.status_code == 200
    sent = billing.calls.last.request.headers
    assert sent["x-tenant-id"] == TENANT_A and sent["x-tenant-slug"] == "acme"
    # headers de identidade forjados pelo cliente foram descartados e substituídos pelos verificados
    assert sent["x-user-id"] == "u_alice" and sent["x-user-role"] == "editor" and sent["x-tenant-role"] == "analyst"
    assert resp.headers["x-tenant-id"] == TENANT_A


@pytest.mark.asyncio
async def test_slug_is_canonicalized_to_tenant_id():
    with respx.mock(assert_all_called=True) as mock:
        mock_session(mock)
        mock_membership(mock, "acme", "u_alice", "viewer", slug="acme").mock(
            return_value=httpx.Response(200, json={"tenant_id": TENANT_A, "tenant_slug": "acme", "tier": "team", "role": "viewer"})
        )
        reports = mock.get(f"{settings.bi_report_service_url}/reports").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get("/api/v1/reports", headers={**COOKIE, "X-Tenant-Slug": "acme"})
    assert resp.status_code == 200
    assert reports.calls.last.request.headers["x-tenant-id"] == TENANT_A


@pytest.mark.asyncio
async def test_default_tenant_is_open_to_any_authenticated_user_but_not_to_anonymous():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        reports = mock.get(f"{settings.bi_report_service_url}/reports").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            ok = await client.get("/api/v1/reports", headers=COOKIE)  # sem header -> tenant default
            anon = await client.get("/api/v1/reports")
    assert ok.status_code == 200 and reports.calls.last.request.headers["x-tenant-id"] == settings.default_tenant_id
    assert anon.status_code == 401


# ---------------------------------------------------------------------------
# Papéis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [("owner", 201), ("admin", 201), ("analyst", 403), ("viewer", 403)])
async def test_admin_only_actions_require_owner_or_admin(role, expected):
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", role)
        mock.post(f"{settings.auth_service_url}/tenants/{TENANT_A}/invitations").mock(return_value=httpx.Response(201, json={}))
        async with gateway() as client:
            resp = await client.post(f"/api/v1/tenants/{TENANT_A}/invitations", json={"email": "x@y.z", "role": "viewer"}, headers=COOKIE)
    assert resp.status_code == expected


@pytest.mark.asyncio
async def test_billing_checkout_requires_tenant_admin_but_reading_does_not():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "viewer")
        mock.post(f"{settings.billing_service_url}/billing/checkout").mock(return_value=httpx.Response(200, json={}))
        mock.get(f"{settings.billing_service_url}/billing/plans").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            checkout = await client.post("/api/v1/billing/checkout", json={}, headers={**COOKIE, "X-Tenant-ID": TENANT_A})
            plans = await client.get("/api/v1/billing/plans", headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert checkout.status_code == 403 and plans.status_code == 200


@pytest.mark.asyncio
async def test_path_tenant_wins_over_header_tenant():
    """Ler /tenants/B/members com header apontando para um tenant próprio não pode funcionar."""
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "owner")
        mock_not_member(mock, TENANT_B, "u_alice")
        members = mock.get(f"{settings.auth_service_url}/tenants/{TENANT_B}/members").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get(f"/api/v1/tenants/{TENANT_B}/members", headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert resp.status_code == 403 and not members.called


# ---------------------------------------------------------------------------
# Endpoints internos e escalonamento de privilégio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("PATCH", f"/api/v1/tenants/{TENANT_A}/tier"),     # upgrade grátis
    ("POST", "/api/v1/audit/events"),                   # forjar auditoria
    ("POST", "/api/v1/auth/token"),                     # emitir token sem autenticar
    ("GET", f"/api/v1/tenants/{TENANT_A}/access/u_alice"),
])
async def test_internal_endpoints_are_blocked_even_for_admins(method, path):
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock, ADMIN)
        mock_membership(mock, TENANT_A, "u_root", "owner")
        downstream = mock.route(host=httpx.URL(settings.auth_service_url).host).mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            resp = await client.request(method, path, json={"tier": "enterprise"}, headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert resp.status_code == 403
    assert "internal" in resp.json()["detail"]
    assert not any(c.request.method == "PATCH" for c in downstream.calls)


@pytest.mark.asyncio
async def test_cannot_create_tenant_owned_by_someone_else():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        create = mock.post(f"{settings.auth_service_url}/tenants").mock(return_value=httpx.Response(201, json={"id": TENANT_A}))
        async with gateway() as client:
            bad = await client.post("/api/v1/tenants", json={"name": "X", "owner_id": "u_victim", "owner_email": "v@x.io"}, headers=COOKIE)
            good = await client.post("/api/v1/tenants", json={"name": "X", "owner_id": "u_alice", "owner_email": "a@x.io"}, headers=COOKIE)
    assert bad.status_code == 403 and good.status_code == 201 and create.call_count == 1


@pytest.mark.asyncio
async def test_invitation_can_only_be_accepted_as_yourself():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        accept = mock.post(f"{settings.auth_service_url}/tenants/invitations/tok123/accept").mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            bad = await client.post("/api/v1/tenants/invitations/tok123/accept", json={"user_id": "u_someone_else"}, headers=COOKIE)
            good = await client.post("/api/v1/tenants/invitations/tok123/accept", json={"user_id": "u_alice"}, headers=COOKIE)
    assert bad.status_code == 403 and good.status_code == 200 and accept.call_count == 1


# ---------------------------------------------------------------------------
# Auditoria: sempre escopada ao tenant autorizado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_read_cannot_target_another_tenant():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "admin")
        mock_not_member(mock, TENANT_B, "u_alice")
        events = mock.get(f"{settings.audit_service_url}/audit/events").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            other = await client.get(f"/api/v1/audit/events?tenant_id={TENANT_B}", headers=COOKIE)
            assert other.status_code == 403 and not events.called

            own = await client.get(f"/api/v1/audit/events?tenant_id={TENANT_A}", headers=COOKIE)
            assert own.status_code == 200
    assert events.calls.last.request.url.params["tenant_id"] == TENANT_A


@pytest.mark.asyncio
async def test_audit_verify_without_tenant_is_scoped_to_header_tenant():
    with respx.mock(assert_all_called=True) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "owner")
        verify = mock.get(f"{settings.audit_service_url}/audit/verify").mock(return_value=httpx.Response(200, json={"valid": True}))
        async with gateway() as client:
            resp = await client.get("/api/v1/audit/verify", headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert resp.status_code == 200
    assert verify.calls.last.request.url.params["tenant_id"] == TENANT_A


@pytest.mark.asyncio
async def test_audit_requires_admin_role():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock_membership(mock, TENANT_A, "u_alice", "analyst")
        mock.get(f"{settings.audit_service_url}/audit/events").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get(f"/api/v1/audit/events?tenant_id={TENANT_A}", headers=COOKIE)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Públicas, falha fechada e cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_public_routes_need_no_session_and_never_forward_spoofed_identity():
    with respx.mock(assert_all_called=True) as mock:
        login = mock.post(f"{settings.data_api_url}/auth/login").mock(return_value=httpx.Response(200, json={}))
        hook = mock.post(f"{settings.billing_service_url}/billing/webhook").mock(return_value=httpx.Response(200, json={}))
        async with gateway() as client:
            r1 = await client.post("/api/v1/auth/login", json={"username": "a", "password": "b"}, headers={"X-User-Role": "admin"})
            r2 = await client.post("/api/v1/billing/webhook", json={}, headers={"Stripe-Signature": "t=1,v1=x"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert "x-user-role" not in login.calls.last.request.headers


@pytest.mark.asyncio
async def test_fails_closed_when_identity_service_is_down():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{settings.data_api_url}/auth/me").mock(side_effect=httpx.ConnectError("down"))
        billing = mock.get(f"{settings.billing_service_url}/billing/plans").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/plans", headers=COOKIE)
    assert resp.status_code == 503 and not billing.called


@pytest.mark.asyncio
async def test_fails_closed_when_tenant_service_is_down():
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        mock.get(f"{settings.auth_service_url}/tenants/{TENANT_A}/access/u_alice").mock(side_effect=httpx.ConnectError("down"))
        billing = mock.get(f"{settings.billing_service_url}/billing/plans").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/plans", headers={**COOKIE, "X-Tenant-ID": TENANT_A})
    assert resp.status_code == 503 and not billing.called


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/billing/../tenants/x/tier", "/api/v1//tenants/x", "/api/v1/a%2f..%2fb"])
async def test_path_traversal_attempt_is_rejected_before_any_lookup(path):
    # (o cliente HTTP normaliza `..` antes de enviar, então chamamos a decisão diretamente)
    async with httpx.AsyncClient() as http:
        decision = await authz.authorize(
            method="GET", path=path, target_url=settings.billing_service_url + "/x", headers=COOKIE,
            query_params={}, host=None, body=b"", client=http,
        )
    assert not decision.allowed and decision.status == 400


@pytest.mark.asyncio
async def test_membership_cache_avoids_repeat_lookups_but_only_for_members(monkeypatch):
    monkeypatch.setattr(settings, "authz_cache_ttl_s", 60.0)
    with respx.mock(assert_all_called=False) as mock:
        mock_session(mock)
        access = mock_membership(mock, TENANT_A, "u_alice", "analyst")
        mock.get(f"{settings.billing_service_url}/billing/plans").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            for _ in range(3):
                assert (await client.get("/api/v1/billing/plans", headers={**COOKIE, "X-Tenant-ID": TENANT_A})).status_code == 200
        assert access.call_count == 1

        # negativas NÃO são cacheadas: quem acabou de aceitar um convite não fica bloqueado
        denied = mock_not_member(mock, TENANT_B, "u_alice")
        async with gateway() as client:
            for _ in range(2):
                await client.get("/api/v1/billing/plans", headers={**COOKIE, "X-Tenant-ID": TENANT_B})
        assert denied.call_count == 2


@pytest.mark.asyncio
async def test_authz_disabled_keeps_legacy_behaviour(monkeypatch):
    monkeypatch.setattr(settings, "authz_enabled", False)
    with respx.mock(assert_all_called=True) as mock:
        plans = mock.get(f"{settings.billing_service_url}/billing/plans").mock(return_value=httpx.Response(200, json=[]))
        async with gateway() as client:
            resp = await client.get("/api/v1/billing/plans", headers={"X-Tenant-ID": "qualquer"})
    assert resp.status_code == 200 and plans.calls.last.request.headers["x-tenant-id"] == "qualquer"
