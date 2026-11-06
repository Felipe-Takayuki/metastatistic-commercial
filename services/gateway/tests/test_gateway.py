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

    # Data API
    assert determine_target_url("/api/v1/datasets") == f"{settings.data_api_url}/datasets"
    assert determine_target_url("/api/v1/analyses/run") == f"{settings.data_api_url}/analyses/run"
    assert determine_target_url("/datasets/123") == f"{settings.data_api_url}/datasets/123"


@pytest.mark.asyncio
async def test_health_check_endpoint():
    async with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(f"{settings.auth_service_url}/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
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
