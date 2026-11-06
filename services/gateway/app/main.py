from contextlib import asynccontextmanager
from typing import Optional
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.proxy import proxy_request
from app.tenant_resolver import tenant_middleware

http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=60.0)
    yield
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="MetaStatistic API Gateway",
    version="0.1.0",
    description="Multi-Tenant API Gateway and Reverse Proxy for MetaStatistic Microservices",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(tenant_middleware)


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    return {"status": "ready"}


@app.get("/health")
async def health_check():
    """Verifica a saúde do gateway e dos serviços downstream."""
    global http_client
    client = http_client or httpx.AsyncClient(timeout=3.0)
    downstream = {}
    all_ok = True

    # 1. Auth & Tenant Service
    try:
        resp = await client.get(f"{settings.auth_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["auth_tenant_service"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["auth_tenant_service"] = "unreachable"
        all_ok = False

    # 2. Data API Service
    try:
        resp = await client.get(f"{settings.data_api_url.rstrip('/')}/health", timeout=2.0)
        downstream["data_api"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["data_api"] = "unreachable"
        all_ok = False

    return {
        "status": "healthy" if all_ok else "degraded",
        "service": "gateway",
        "version": "0.1.0",
        "downstream": downstream,
    }


# Proxy para todos os caminhos /api/v1/*
@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_api_v1(request: Request, path: str) -> Response:
    global http_client
    full_path = f"/api/v1/{path}"
    return await proxy_request(request, full_path, client=http_client)


# Proxy para rotas diretas de auth e tenants
@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_auth(request: Request, path: str) -> Response:
    global http_client
    return await proxy_request(request, f"/auth/{path}", client=http_client)


@app.api_route("/tenants/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_tenants(request: Request, path: str) -> Response:
    global http_client
    return await proxy_request(request, f"/tenants/{path}", client=http_client)


# Proxy para rotas diretas de datasets, queries, analyses, reports, dashboards, transforms
@app.api_route("/{prefix}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_direct(request: Request, prefix: str, path: str) -> Response:
    global http_client
    if prefix in {"datasets", "queries", "analyses", "reports", "dashboards", "transforms", "collections"}:
        return await proxy_request(request, f"/{prefix}/{path}", client=http_client)
    return Response(
        content=b'{"error": "Not Found", "detail": "Route not mapped in gateway"}',
        status_code=404,
        media_type="application/json",
    )
