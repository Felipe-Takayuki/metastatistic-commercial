import base64
import json
import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.proxy import determine_target_url
from app.tenant_resolver import extract_jwt_tenant_id, extract_subdomain, resolve_tenant


def test_subdomain_extraction():
    assert extract_subdomain("acme.metastatistic.com") == "acme"
    assert extract_subdomain("hospital-sph.metastatistic.io:8080") == "hospital-sph"
    assert extract_subdomain("acme.localhost") == "acme"
    # Reservados devem retornar None
    assert extract_subdomain("localhost") is None
    assert extract_subdomain("localhost:8080") is None
    assert extract_subdomain("127.0.0.1:8000") is None
    assert extract_subdomain("api.metastatistic.com") is None
    assert extract_subdomain("web.metastatistic.com") is None
    assert extract_subdomain("gateway.metastatistic.com") is None


def test_jwt_tenant_id_extraction():
    # Cria payload base64url simples
    payload = {"sub": "u1", "tenant_id": "org_jwt_99", "role": "analyst"}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    token = f"fakeheader.{payload_b64}.fakesig"

    assert extract_jwt_tenant_id(f"Bearer {token}") == "org_jwt_99"
    assert extract_jwt_tenant_id("Bearer invalidtoken") is None
    assert extract_jwt_tenant_id(None) is None


def test_tenant_resolution_precedence():
    # 1. Header direto tem prioridade máxima
    t_id, t_slug = resolve_tenant(
        {"X-Tenant-ID": "header_tenant", "Host": "subdomain.metastatistic.com"},
        host="subdomain.metastatistic.com",
    )
    assert t_id == "header_tenant"

    # 2. Subdomínio quando não há header
    t_id, t_slug = resolve_tenant({}, host="clinic-a.metastatistic.com")
    assert t_id == "clinic-a"
    assert t_slug == "clinic-a"

    # 3. JWT quando não há header nem subdomínio
    payload = {"tenant_id": "jwt_org_42"}
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    auth_header = f"Bearer header.{p_b64}.sig"
    t_id, _ = resolve_tenant({"Authorization": auth_header}, host="localhost:8080")
    assert t_id == "jwt_org_42"

    # 4. Fallback padrão
    t_id, _ = resolve_tenant({}, host="localhost:8080")
    assert t_id == "default"


def test_determine_target_url():
    # Frontend Auth (Data API: cookies, sessão e gestão)
    assert determine_target_url("/api/v1/auth/status") == f"{settings.data_api_url}/auth/status"
    assert determine_target_url("/api/auth/status") == f"{settings.data_api_url}/auth/status"
    assert determine_target_url("/auth/status") == f"{settings.data_api_url}/auth/status"
    assert determine_target_url("/api/v1/auth/login") == f"{settings.data_api_url}/auth/login"
    assert determine_target_url("/auth/login") == f"{settings.data_api_url}/auth/login"
    assert determine_target_url("/api/v1/auth/logout") == f"{settings.data_api_url}/auth/logout"
    assert determine_target_url("/auth/logout") == f"{settings.data_api_url}/auth/logout"
    assert determine_target_url("/api/v1/auth/setup") == f"{settings.data_api_url}/auth/setup"
    assert determine_target_url("/auth/setup") == f"{settings.data_api_url}/auth/setup"
    assert determine_target_url("/api/v1/auth/register") == f"{settings.data_api_url}/auth/register"
    assert determine_target_url("/api/auth/register") == f"{settings.data_api_url}/auth/register"
    assert determine_target_url("/auth/register") == f"{settings.data_api_url}/auth/register"
    assert determine_target_url("/api/v1/auth/password") == f"{settings.data_api_url}/auth/password"
    assert determine_target_url("/auth/password") == f"{settings.data_api_url}/auth/password"
    assert determine_target_url("/api/v1/auth/directory") == f"{settings.data_api_url}/auth/directory"
    assert determine_target_url("/auth/directory") == f"{settings.data_api_url}/auth/directory"
    assert determine_target_url("/api/v1/auth/me") == f"{settings.data_api_url}/auth/me"
    assert determine_target_url("/auth/me") == f"{settings.data_api_url}/auth/me"

    # Auth e Tenants (Auth Service: tokens JWT, SSO, SCIM)
    assert determine_target_url("/api/v1/auth/token") == f"{settings.auth_service_url}/auth/token"
    assert determine_target_url("/auth/token") == f"{settings.auth_service_url}/auth/token"
    assert determine_target_url("/api/v1/auth/verify") == f"{settings.auth_service_url}/auth/verify"
    assert determine_target_url("/auth/verify") == f"{settings.auth_service_url}/auth/verify"
    assert determine_target_url("/api/v1/tenants/t123") == f"{settings.auth_service_url}/tenants/t123"
    assert determine_target_url("/tenants/t123") == f"{settings.auth_service_url}/tenants/t123"

    # Stat Orchestrator
    assert determine_target_url("/api/v1/analyses/run") == f"{settings.stat_orchestrator_url}/analyses/run"
    assert determine_target_url("/analyses/status") == f"{settings.stat_orchestrator_url}/analyses/status"
    assert determine_target_url("/api/v1/jobs/submit") == f"{settings.stat_orchestrator_url}/jobs/submit"

    # Data Engine (queries, transforms, connections)
    assert determine_target_url("/api/v1/queries/run") == f"{settings.data_engine_service_url}/queries/run"
    assert determine_target_url("/queries/arrow") == f"{settings.data_engine_service_url}/queries/arrow"
    assert determine_target_url("/api/v1/transforms/preview") == f"{settings.data_engine_service_url}/transforms/preview"
    assert determine_target_url("/transforms/preview") == f"{settings.data_engine_service_url}/transforms/preview"
    assert determine_target_url("/api/v1/connections") == f"{settings.data_engine_service_url}/connections"
    assert determine_target_url("/connections/test") == f"{settings.data_engine_service_url}/connections/test"

    # Data API
    assert determine_target_url("/api/v1/datasets") == f"{settings.data_api_url}/datasets"
    assert determine_target_url("/datasets/123") == f"{settings.data_api_url}/datasets/123"

    # BI Reports & Dashboards
    assert determine_target_url("/api/v1/reports") == f"{settings.bi_report_service_url}/reports"
    assert determine_target_url("/api/v1/reports/rep_1/snapshots") == f"{settings.bi_report_service_url}/reports/rep_1/snapshots"
    assert determine_target_url("/reports/rep_1") == f"{settings.bi_report_service_url}/reports/rep_1"
    assert determine_target_url("/api/v1/dashboards") == f"{settings.bi_report_service_url}/dashboards"
    assert determine_target_url("/dashboards/dash_1") == f"{settings.bi_report_service_url}/dashboards/dash_1"
    assert determine_target_url("/ws/reports/rep_1") == f"{settings.bi_report_service_url}/ws/reports/rep_1"

    # Export Service
    assert determine_target_url("/api/v1/export/generate") == f"{settings.export_service_url}/export/generate"
    assert determine_target_url("/export/docx") == f"{settings.export_service_url}/export/docx"

    # Billing Service (Stripe)
    assert determine_target_url("/api/v1/billing/plans") == f"{settings.billing_service_url}/billing/plans"
    assert determine_target_url("/billing/checkout") == f"{settings.billing_service_url}/billing/checkout"
    assert determine_target_url("/billing/subscription") == f"{settings.billing_service_url}/billing/subscription"

    # Enterprise: SSO, SCIM 2.0 e Trilha de Auditoria Imutável
    assert determine_target_url("/api/v1/sso/login") == f"{settings.auth_service_url}/auth/sso/login"
    assert determine_target_url("/sso/saml/acs") == f"{settings.auth_service_url}/auth/sso/saml/acs"
    assert determine_target_url("/scim/v2/tenants/t1/ServiceProviderConfig") == f"{settings.auth_service_url}/scim/v2/tenants/t1/ServiceProviderConfig"
    assert determine_target_url("/api/v1/scim/v2/tenants/t1/Users") == f"{settings.auth_service_url}/scim/v2/tenants/t1/Users"
    assert determine_target_url("/api/v1/audit/events") == f"{settings.auth_service_url}/audit/events"
    assert determine_target_url("/audit/verify") == f"{settings.auth_service_url}/audit/verify"

    # Web Frontend & Static Assets (Unificação de acesso único via Gateway)
    assert determine_target_url("/") == f"{settings.web_url}/"
    assert determine_target_url("/assets/index.js") == f"{settings.web_url}/assets/index.js"
    assert determine_target_url("/assets/style.css") == f"{settings.web_url}/assets/style.css"
    assert determine_target_url("/favicon.ico") == f"{settings.web_url}/favicon.ico"
    assert determine_target_url("/vite.svg") == f"{settings.web_url}/vite.svg"
    assert determine_target_url("/index.html") == f"{settings.web_url}/index.html"
    assert determine_target_url("/app-route") == f"{settings.web_url}/app-route"
    assert determine_target_url("/api/billing/plans") == f"{settings.billing_service_url}/billing/plans"
    assert determine_target_url("/api/datasets") == f"{settings.data_api_url}/datasets"


@pytest.mark.asyncio
async def test_health_check_endpoint():
    async with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(f"{settings.auth_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        respx_mock.get(f"{settings.stat_orchestrator_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        respx_mock.get(f"{settings.data_engine_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        respx_mock.get(f"{settings.data_api_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        respx_mock.get(f"{settings.bi_report_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        respx_mock.get(f"{settings.export_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        respx_mock.get(f"{settings.billing_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["downstream"]["auth_tenant_service"] == "healthy"
            assert data["downstream"]["stat_orchestrator"] == "healthy"
            assert data["downstream"]["data_engine"] == "healthy"
            assert data["downstream"]["bi_report_service"] == "healthy"
            assert data["downstream"]["export_service"] == "healthy"
            assert data["downstream"]["billing_service"] == "healthy"
            assert data["downstream"]["data_api"] == "healthy"


@pytest.mark.asyncio
async def test_proxy_routing_and_tenant_header_forwarding():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock do Auth service
        auth_route = respx_mock.post(f"{settings.auth_service_url}/auth/token").mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "token123", "role": "admin"},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock do Data API
        data_route = respx_mock.get(f"{settings.data_api_url}/datasets").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "ds_1", "name": "Clinical Data"}],
                headers={"Content-Type": "application/json"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. Requisição para /api/v1/auth/token com host subdomínio
            resp_auth = await client.post(
                "/api/v1/auth/token",
                json={"user_id": "doc1"},
                headers={"Host": "hospital-sph.metastatistic.com"},
            )
            assert resp_auth.status_code == 200
            assert resp_auth.json()["access_token"] == "token123"
            assert resp_auth.headers.get("X-Tenant-ID") == "hospital-sph"

            # Valida que o downstream recebeu o X-Tenant-ID
            assert auth_route.calls.last.request.headers.get("x-tenant-id") == "hospital-sph"

            # 2. Requisição para /api/v1/datasets com header X-Tenant-ID explícito
            resp_data = await client.get(
                "/api/v1/datasets",
                headers={"X-Tenant-ID": "tenant_custom_42"},
            )
            assert resp_data.status_code == 200
            assert resp_data.json()[0]["id"] == "ds_1"
            assert resp_data.headers.get("X-Tenant-ID") == "tenant_custom_42"
            assert data_route.calls.last.request.headers.get("x-tenant-id") == "tenant_custom_42"


@pytest.mark.asyncio
async def test_proxy_error_handling_downstream_unavailable():
    async with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.get(f"{settings.data_api_url}/datasets").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            resp = await client.get("/api/v1/datasets")
            assert resp.status_code == 502
            assert "Bad Gateway" in resp.json()["error"]


@pytest.mark.asyncio
async def test_proxy_routing_to_data_engine_service():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock de queries/run
        query_route = respx_mock.post(f"{settings.data_engine_service_url}/queries/run").mock(
            return_value=httpx.Response(
                200,
                json={"columns": [{"name": "cnt", "type": "INTEGER"}], "rows": [{"cnt": 42}], "row_count": 1, "execution_time_ms": 1.5},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock de transforms/preview
        transform_route = respx_mock.post(f"{settings.data_engine_service_url}/transforms/preview").mock(
            return_value=httpx.Response(
                200,
                json={"columns": [{"name": "id", "type": "INTEGER"}], "rows": [{"id": 1}], "row_count": 1},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock de connections
        connections_route = respx_mock.get(f"{settings.data_engine_service_url}/connections").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "c1", "name": "Warehouse DB", "type": "sqlite"}],
                headers={"Content-Type": "application/json"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. /api/v1/queries/run
            resp_q = await client.post(
                "/api/v1/queries/run",
                json={"sql": "SELECT COUNT(*) AS cnt FROM dataset"},
                headers={"X-Tenant-ID": "tenant_alpha"},
            )
            assert resp_q.status_code == 200
            assert resp_q.json()["rows"][0]["cnt"] == 42
            assert query_route.calls.last.request.headers.get("x-tenant-id") == "tenant_alpha"

            # 2. /api/v1/transforms/preview
            resp_t = await client.post(
                "/api/v1/transforms/preview",
                json={"dataset_id": "ds_1", "steps": []},
                headers={"X-Tenant-ID": "tenant_beta"},
            )
            assert resp_t.status_code == 200
            assert resp_t.json()["row_count"] == 1
            assert transform_route.calls.last.request.headers.get("x-tenant-id") == "tenant_beta"

            # 3. /api/v1/connections
            resp_c = await client.get(
                "/api/v1/connections",
                headers={"X-Tenant-ID": "tenant_gamma"},
            )
            assert resp_c.status_code == 200
            assert resp_c.json()[0]["id"] == "c1"
            assert connections_route.calls.last.request.headers.get("x-tenant-id") == "tenant_gamma"


@pytest.mark.asyncio
async def test_proxy_routing_to_bi_reports_and_export_service():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock de reports
        report_route = respx_mock.post(f"{settings.bi_report_service_url}/reports").mock(
            return_value=httpx.Response(
                201,
                json={"id": "rep_100", "title": "Trial 1", "version": 1, "blocks": []},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock de dashboards
        dashboard_route = respx_mock.get(f"{settings.bi_report_service_url}/dashboards/dash_200").mock(
            return_value=httpx.Response(
                200,
                json={"id": "dash_200", "title": "KPIs", "version": 1, "tiles": []},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock de export
        export_route = respx_mock.post(f"{settings.export_service_url}/export/generate").mock(
            return_value=httpx.Response(
                200,
                json={"filename": "report.html", "format": "html", "content": "<html>APA</html>"},
                headers={"Content-Type": "application/json"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. /api/v1/reports
            resp_rep = await client.post(
                "/api/v1/reports",
                json={"title": "Trial 1", "blocks": []},
                headers={"X-Tenant-ID": "tenant_medical"},
            )
            assert resp_rep.status_code == 201
            assert resp_rep.json()["id"] == "rep_100"
            assert report_route.calls.last.request.headers.get("x-tenant-id") == "tenant_medical"

            # 2. /api/v1/dashboards/dash_200
            resp_dash = await client.get(
                "/api/v1/dashboards/dash_200",
                headers={"X-Tenant-ID": "tenant_medical"},
            )
            assert resp_dash.status_code == 200
            assert resp_dash.json()["id"] == "dash_200"
            assert dashboard_route.calls.last.request.headers.get("x-tenant-id") == "tenant_medical"

            # 3. /api/v1/export/generate
            resp_exp = await client.post(
                "/api/v1/export/generate",
                json={"title": "Report", "format": "html", "blocks": []},
                headers={"X-Tenant-ID": "tenant_medical"},
            )
            assert resp_exp.status_code == 200
            assert resp_exp.json()["format"] == "html"
            assert export_route.calls.last.request.headers.get("x-tenant-id") == "tenant_medical"


@pytest.mark.asyncio
async def test_proxy_routing_to_enterprise_sso_scim_audit():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock SSO login
        sso_route = respx_mock.post(f"{settings.auth_service_url}/auth/sso/login").mock(
            return_value=httpx.Response(
                200,
                json={"auth_url": "https://idp.okta.com/sso", "provider_type": "saml"},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock SCIM Users
        scim_route = respx_mock.get(f"{settings.auth_service_url}/scim/v2/tenants/t_corp/Users").mock(
            return_value=httpx.Response(
                200,
                json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": 0, "Resources": []},
                headers={"Content-Type": "application/scim+json"},
            )
        )

        # Mock Audit Verify
        audit_route = respx_mock.get(f"{settings.auth_service_url}/audit/verify").mock(
            return_value=httpx.Response(
                200,
                json={"valid": True, "total_records": 10, "verified_at": "2026-11-09T00:00:00Z"},
                headers={"Content-Type": "application/json"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. /api/v1/sso/login
            resp_sso = await client.post(
                "/api/v1/sso/login",
                json={"tenant_id": "t_corp"},
                headers={"X-Tenant-ID": "t_corp"},
            )
            assert resp_sso.status_code == 200
            assert resp_sso.json()["provider_type"] == "saml"
            assert sso_route.calls.last.request.headers.get("x-tenant-id") == "t_corp"

            # 2. /scim/v2/tenants/t_corp/Users
            resp_scim = await client.get(
                "/scim/v2/tenants/t_corp/Users",
                headers={"X-Tenant-ID": "t_corp"},
            )
            assert resp_scim.status_code == 200
            assert "application/scim+json" in resp_scim.headers["content-type"]
            assert scim_route.calls.last.request.headers.get("x-tenant-id") == "t_corp"

            # 3. /api/v1/audit/verify
            resp_audit = await client.get(
                "/api/v1/audit/verify",
                headers={"X-Tenant-ID": "t_corp"},
            )
            assert resp_audit.status_code == 200
            assert resp_audit.json()["valid"] is True
            assert audit_route.calls.last.request.headers.get("x-tenant-id") == "t_corp"


@pytest.mark.asyncio
async def test_proxy_routing_to_billing_service():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock /billing/plans
        plans_route = respx_mock.get(f"{settings.billing_service_url}/billing/plans").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "team", "price_monthly": 4900}],
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock /billing/checkout
        checkout_route = respx_mock.post(f"{settings.billing_service_url}/billing/checkout").mock(
            return_value=httpx.Response(
                200,
                json={"session_id": "cs_test_gw", "url": "https://checkout.stripe.com/c/pay/cs_test_gw"},
                headers={"Content-Type": "application/json"},
            )
        )

        # Mock /billing/subscription
        sub_route = respx_mock.get(f"{settings.billing_service_url}/billing/subscription").mock(
            return_value=httpx.Response(
                200,
                json={"id": "sub_gw", "tier": "team", "status": "active"},
                headers={"Content-Type": "application/json"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. /api/v1/billing/plans
            resp_plans = await client.get("/api/v1/billing/plans")
            assert resp_plans.status_code == 200
            assert resp_plans.json()[0]["id"] == "team"

            # 2. /billing/checkout via prefix route
            resp_checkout = await client.post(
                "/billing/checkout",
                json={"plan_id": "team"},
                headers={"X-Tenant-ID": "tenant_gw"},
            )
            assert resp_checkout.status_code == 200
            assert resp_checkout.json()["session_id"] == "cs_test_gw"
            assert checkout_route.calls.last.request.headers.get("x-tenant-id") == "tenant_gw"

            # 3. /billing/subscription
            resp_sub = await client.get(
                "/billing/subscription",
                headers={"X-Tenant-ID": "tenant_gw"},
            )
            assert resp_sub.status_code == 200
            assert resp_sub.json()["tier"] == "team"
            assert sub_route.calls.last.request.headers.get("x-tenant-id") == "tenant_gw"


@pytest.mark.asyncio
async def test_proxy_routing_to_web_frontend():
    async with respx.mock(assert_all_called=True) as respx_mock:
        # Mock raiz /
        root_route = respx_mock.get(f"{settings.web_url}/").mock(
            return_value=httpx.Response(
                200,
                text="<!DOCTYPE html><html><head><title>MetaStatistic</title></head><body><div id='root'></div></body></html>",
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        )

        # Mock /assets/index.js
        asset_route = respx_mock.get(f"{settings.web_url}/assets/index.js").mock(
            return_value=httpx.Response(
                200,
                text="console.log('metastatistic web');",
                headers={"Content-Type": "application/javascript"},
            )
        )

        # Mock /favicon.ico
        favicon_route = respx_mock.get(f"{settings.web_url}/favicon.ico").mock(
            return_value=httpx.Response(
                200,
                content=b"\x00\x00\x01\x00",
                headers={"Content-Type": "image/x-icon"},
            )
        )

        # Mock rota SPA arbitrária (/explore-view)
        spa_route = respx_mock.get(f"{settings.web_url}/explore-view").mock(
            return_value=httpx.Response(
                200,
                text="<!DOCTYPE html><html><body>SPA Fallback</body></html>",
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            # 1. GET /
            resp_root = await client.get("/")
            assert resp_root.status_code == 200
            assert "MetaStatistic" in resp_root.text
            assert root_route.called

            # 2. GET /assets/index.js
            resp_asset = await client.get("/assets/index.js")
            assert resp_asset.status_code == 200
            assert "metastatistic web" in resp_asset.text
            assert asset_route.called

            # 3. GET /favicon.ico
            resp_favicon = await client.get("/favicon.ico")
            assert resp_favicon.status_code == 200
            assert resp_favicon.content == b"\x00\x00\x01\x00"
            assert favicon_route.called

            # 4. GET /explore-view (SPA client route proxying)
            resp_spa = await client.get("/explore-view")
            assert resp_spa.status_code == 200
            assert "SPA Fallback" in resp_spa.text
            assert spa_route.called
