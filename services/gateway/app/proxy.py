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


def determine_target_url(path: str) -> str:
    """
    Roteia o caminho da requisição para o serviço downstream apropriado:
    - /api/v1/auth/* e /api/v1/tenants/* -> AUTH_SERVICE_URL
    - /api/v1/* (datasets, queries, analyses, reports, dashboards, etc.) -> DATA_API_URL
    """
    clean_path = "/" + path.lstrip("/")

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

    # Casos de Data API
    if clean_path.startswith("/api/v1/"):
        target_path = clean_path.replace("/api/v1", "", 1)
        return f"{settings.data_api_url.rstrip('/')}{target_path}"

    # Outros endpoints de dados diretos (/datasets, /queries, /analyses, etc.)
    return f"{settings.data_api_url.rstrip('/')}{clean_path}"


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
