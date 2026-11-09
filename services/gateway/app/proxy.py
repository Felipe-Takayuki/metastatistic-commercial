from typing import Optional
import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from app.config import settings
from app.tenant_resolver import resolve_tenant

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

API_DIRECT_PREFIXES = {
    "api",
    "auth",
    "tenants",
    "datasets",
    "queries",
    "analyses",
    "reports",
    "dashboards",
    "transforms",
    "collections",
    "jobs",
    "connections",
    "export",
    "scim",
    "sso",
    "audit",
    "billing",
    "users",
}


def determine_target_url(path: str) -> str:
    """
    Roteia o caminho da requisição para o serviço downstream apropriado:
    - /, /assets/*, /favicon.ico, /index.html e rotas não-API -> WEB_URL
    - /api/v1/auth/* e /api/v1/tenants/* -> AUTH_SERVICE_URL
    - /api/v1/analyses/* e /api/v1/jobs/* -> STAT_ORCHESTRATOR_URL
    - /api/v1/* (datasets, queries, reports, dashboards, etc.) -> DATA_API_URL
    """
    clean_path = "/" + path.lstrip("/")

    # Casos de Web Frontend e Assets estáticos
    if (
        clean_path in {"/", "", "/favicon.ico", "/robots.txt", "/vite.svg", "/index.html"}
        or clean_path.startswith("/assets/")
    ):
        return f"{settings.web_url.rstrip('/')}{clean_path if clean_path else '/'}"

    # Normaliza rotas /api/* legadas sem prefixo /v1 para /api/v1/*
    if clean_path.startswith("/api/") and not clean_path.startswith("/api/v1/"):
        clean_path = "/api/v1" + clean_path[4:]

    # Rotas de autenticação do Frontend (Data API: cookies, sessão e gestão de usuários)
    frontend_auth_endpoints = (
        "/auth/status",
        "/auth/login",
        "/auth/logout",
        "/auth/setup",
        "/auth/register",
        "/auth/password",
        "/auth/directory",
        "/auth/me",
    )
    for endpoint in frontend_auth_endpoints:
        if clean_path == endpoint or clean_path.startswith(endpoint + "/"):
            return f"{settings.data_api_url.rstrip('/')}{clean_path}"
        v1_endpoint = f"/api/v1{endpoint}"
        if clean_path == v1_endpoint or clean_path.startswith(v1_endpoint + "/"):
            target_path = clean_path.replace("/api/v1", "", 1)
            return f"{settings.data_api_url.rstrip('/')}{target_path}"

    # Casos de Auth e Tenants
    if clean_path.startswith("/api/v1/auth/"):
        target_path = clean_path.replace("/api/v1/auth", "/auth", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"
    elif clean_path == "/api/v1/auth":
        return f"{settings.auth_service_url.rstrip('/')}/auth"
    elif clean_path.startswith("/api/v1/tenants"):
        target_path = clean_path.replace("/api/v1/tenants", "/tenants", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/auth/") or clean_path == "/auth":
        return f"{settings.auth_service_url.rstrip('/')}{clean_path}"
    elif clean_path.startswith("/tenants/") or clean_path == "/tenants":
        return f"{settings.auth_service_url.rstrip('/')}{clean_path}"

    # Casos de Enterprise: SSO, SCIM 2.0 e Audit Trail
    if clean_path.startswith("/api/v1/sso/"):
        target_path = clean_path.replace("/api/v1/sso", "/auth/sso", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"
    elif clean_path == "/api/v1/sso":
        return f"{settings.auth_service_url.rstrip('/')}/auth/sso"
    elif clean_path.startswith("/sso/") or clean_path == "/sso":
        target_path = clean_path.replace("/sso", "/auth/sso", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"

    if clean_path.startswith("/api/v1/scim/"):
        target_path = clean_path.replace("/api/v1/scim", "/scim", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/scim/") or clean_path == "/scim":
        return f"{settings.auth_service_url.rstrip('/')}{clean_path}"

    if clean_path.startswith("/api/v1/audit/"):
        target_path = clean_path.replace("/api/v1/audit", "/audit", 1)
        return f"{settings.auth_service_url.rstrip('/')}{target_path}"
    elif clean_path == "/api/v1/audit":
        return f"{settings.auth_service_url.rstrip('/')}/audit"
    elif clean_path.startswith("/audit/") or clean_path == "/audit":
        return f"{settings.auth_service_url.rstrip('/')}{clean_path}"

    # Casos de Orquestração Estatística e Jobs
    if clean_path.startswith("/api/v1/analyses"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.stat_orchestrator_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/analyses"):
        return f"{settings.stat_orchestrator_url.rstrip('/')}{clean_path}"
    elif clean_path.startswith("/api/v1/jobs"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.stat_orchestrator_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/jobs"):
        return f"{settings.stat_orchestrator_url.rstrip('/')}{clean_path}"

    # Casos de Data Engine (queries, transforms, connections)
    if clean_path.startswith("/api/v1/queries"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.data_engine_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/queries"):
        return f"{settings.data_engine_service_url.rstrip('/')}{clean_path}"

    if clean_path.startswith("/api/v1/transforms"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.data_engine_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/transforms"):
        return f"{settings.data_engine_service_url.rstrip('/')}{clean_path}"

    if clean_path.startswith("/api/v1/connections"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.data_engine_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/connections"):
        return f"{settings.data_engine_service_url.rstrip('/')}{clean_path}"

    # Casos de BI & Relatórios (reports, dashboards, ws)
    if clean_path.startswith("/api/v1/reports"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.bi_report_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/reports"):
        return f"{settings.bi_report_service_url.rstrip('/')}{clean_path}"

    if clean_path.startswith("/api/v1/dashboards"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.bi_report_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/dashboards"):
        return f"{settings.bi_report_service_url.rstrip('/')}{clean_path}"

    if clean_path.startswith("/ws/"):
        return f"{settings.bi_report_service_url.rstrip('/')}{clean_path}"

    # Casos de Exportação Multi-formato
    if clean_path.startswith("/api/v1/export"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.export_service_url.rstrip('/')}{target_path}"
    elif clean_path.startswith("/export"):
        return f"{settings.export_service_url.rstrip('/')}{clean_path}"

    # Casos de Faturamento e Billing Stripe
    if clean_path.startswith("/api/v1/billing/"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.billing_service_url.rstrip('/')}{target_path}"
    elif clean_path == "/api/v1/billing":
        return f"{settings.billing_service_url.rstrip('/')}/billing"
    elif clean_path.startswith("/billing/") or clean_path == "/billing":
        return f"{settings.billing_service_url.rstrip('/')}{clean_path}"

    # Casos de Data API
    if clean_path.startswith("/api/v1/datasets") or clean_path.startswith("/datasets"):
        target_path = clean_path.replace("/api/v1", "", 1) if clean_path.startswith("/api/v1") else clean_path
        return f"{settings.data_api_url.rstrip('/')}{target_path}"

    if clean_path.startswith("/api/v1/collections") or clean_path.startswith("/collections"):
        target_path = clean_path.replace("/api/v1", "", 1) if clean_path.startswith("/api/v1") else clean_path
        return f"{settings.data_api_url.rstrip('/')}{target_path}"

    if clean_path.startswith("/api/v1/users") or clean_path.startswith("/users"):
        target_path = clean_path.replace("/api/v1", "", 1) if clean_path.startswith("/api/v1") else clean_path
        return f"{settings.data_api_url.rstrip('/')}{target_path}"

    if clean_path.startswith("/api/v1/"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.data_api_url.rstrip('/')}{target_path}"

    # Se a rota for um prefixo de API conhecido direto, encaminha para data_api_url
    first_segment = clean_path.lstrip("/").split("/")[0]
    if first_segment in API_DIRECT_PREFIXES:
        return f"{settings.data_api_url.rstrip('/')}{clean_path}"

    # Qualquer rota não-API (SPA, assets, páginas do frontend) vai para o Frontend
    return f"{settings.web_url.rstrip('/')}{clean_path}"


async def proxy_request(request: Request, path: str, client: Optional[httpx.AsyncClient] = None) -> Response:
    """
    Encaminha a requisição assincronamente para o serviço de destino,
    injetando os headers de tenant e preservando o corpo e os parâmetros.
    """
    target_url = determine_target_url(path)
    tenant_id, tenant_slug = resolve_tenant(dict(request.headers), host=request.headers.get("host"))

    # Monta cabeçalhos encaminhados sem duplicatas
    fwd_headers = {}
    for key, value in request.headers.items():
        low_key = key.lower()
        if low_key not in HOP_BY_HOP_HEADERS and low_key not in {"x-tenant-id", "x-tenant-slug"}:
            fwd_headers[key] = value

    # Injeta identificação de tenant canonicalizada
    fwd_headers["X-Tenant-ID"] = tenant_id
    if tenant_slug:
        fwd_headers["X-Tenant-Slug"] = tenant_slug

    # Headers de proxy reverso
    client_host = request.client.host if request.client else "unknown"
    fwd_headers["X-Forwarded-For"] = client_host
    fwd_headers["X-Forwarded-Proto"] = request.url.scheme
    if request.headers.get("host"):
        fwd_headers["X-Forwarded-Host"] = request.headers["host"]

    body = await request.body()
    query_params = dict(request.query_params)

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
        close_client = True

    try:
        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=fwd_headers,
            params=query_params,
            content=body,
        )
        downstream_resp = await client.send(req, stream=True)

        resp_headers = {}
        for key, value in downstream_resp.headers.items():
            low_k = key.lower()
            if low_k not in HOP_BY_HOP_HEADERS and low_k not in {"x-tenant-id", "x-tenant-slug"}:
                resp_headers[key] = value

        resp_headers["X-Tenant-ID"] = tenant_id
        if tenant_slug:
            resp_headers["X-Tenant-Slug"] = tenant_slug

        content = await downstream_resp.aread()
        return Response(
            content=content,
            status_code=downstream_resp.status_code,
            headers=resp_headers,
            media_type=downstream_resp.headers.get("content-type"),
        )
    except httpx.ConnectError:
        return Response(
            content=b'{"error": "Bad Gateway", "detail": "Downstream service unavailable"}',
            status_code=502,
            media_type="application/json",
            headers={"X-Tenant-ID": tenant_id},
        )
    except httpx.TimeoutException:
        return Response(
            content=b'{"error": "Gateway Timeout", "detail": "Downstream service timed out"}',
            status_code=504,
            media_type="application/json",
            headers={"X-Tenant-ID": tenant_id},
        )
    finally:
        if close_client:
            await client.aclose()
