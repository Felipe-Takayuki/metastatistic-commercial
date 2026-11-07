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
    # Auth e Tenants
    assert determine_target_url("/api/v1/auth/token") == f"{settings.auth_service_url}/auth/token"
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

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["downstream"]["auth_tenant_service"] == "healthy"
            assert data["downstream"]["stat_orchestrator"] == "healthy"
            assert data["downstream"]["data_engine"] == "healthy"
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
