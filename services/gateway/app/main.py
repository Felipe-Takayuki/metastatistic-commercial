import asyncio
from contextlib import asynccontextmanager
from typing import Optional
import httpx
import websockets
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.authz import fetch_identity
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

    # 2. Stat Orchestrator Service
    try:
        resp = await client.get(f"{settings.stat_orchestrator_url.rstrip('/')}/health", timeout=2.0)
        downstream["stat_orchestrator"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["stat_orchestrator"] = "unreachable"
        all_ok = False

    # 3. Data Engine Service
    try:
        resp = await client.get(f"{settings.data_engine_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["data_engine"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["data_engine"] = "unreachable"
        all_ok = False

    # 4. BI Report Service
    try:
        resp = await client.get(f"{settings.bi_report_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["bi_report_service"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["bi_report_service"] = "unreachable"
        all_ok = False

    # 5. Export Service
    try:
        resp = await client.get(f"{settings.export_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["export_service"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["export_service"] = "unreachable"
        all_ok = False

    # 6. Data API Service
    try:
        resp = await client.get(f"{settings.data_api_url.rstrip('/')}/health", timeout=2.0)
        downstream["data_api"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["data_api"] = "unreachable"
        all_ok = False

    # 7. Billing Service
    try:
        resp = await client.get(f"{settings.billing_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["billing_service"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["billing_service"] = "unreachable"
        all_ok = False

    # 8. Audit Service
    try:
        resp = await client.get(f"{settings.audit_service_url.rstrip('/')}/health", timeout=2.0)
        downstream["audit_service"] = "healthy" if resp.status_code == 200 else f"status_{resp.status_code}"
    except Exception:
        downstream["audit_service"] = "unreachable"
        all_ok = False

    return {
        "status": "healthy" if all_ok else "degraded",
        "service": "gateway",
        "version": "0.1.0",
        "downstream": downstream,
    }


# Proxy para rota raiz (Frontend)
@app.api_route("/", methods=["GET", "HEAD"])
async def route_root(request: Request) -> Response:
    global http_client
    return await proxy_request(request, "/", client=http_client)


# Proxy para todos os caminhos /api/v1/*
@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_api_v1(request: Request, path: str) -> Response:
    global http_client
    full_path = f"/api/v1/{path}"
    return await proxy_request(request, full_path, client=http_client)


# Proxy para compatibilidade com rotas /api/*
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_api(request: Request, path: str) -> Response:
    global http_client
    full_path = f"/api/{path}"
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


# Proxy para assets estáticos do frontend (/assets/*)
@app.api_route("/assets/{path:path}", methods=["GET", "HEAD"])
async def route_assets(request: Request, path: str) -> Response:
    global http_client
    return await proxy_request(request, f"/assets/{path}", client=http_client)


# Proxy para rotas diretas de microserviços e rotas SPA do frontend
@app.api_route("/{prefix}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def route_direct(request: Request, prefix: str, path: str) -> Response:
    global http_client
    return await proxy_request(request, f"/{prefix}/{path}", client=http_client)


# Proxy para arquivos estáticos na raiz (favicon.ico, vite.svg, robots.txt, etc.)
@app.api_route("/{filename:str}", methods=["GET", "HEAD"])
async def route_root_files(request: Request, filename: str) -> Response:
    global http_client
    return await proxy_request(request, f"/{filename}", client=http_client)


# Proxy para WebSocket de colaboração em tempo real
@app.websocket("/ws/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    if settings.authz_enabled:
        # O handshake do WebSocket leva o cookie de sessão; sem sessão válida, recusa antes de aceitar a conexão.
        client = http_client or httpx.AsyncClient(timeout=5.0)
        identity, failure = await fetch_identity(client, websocket.headers.get("cookie"))
        if failure or not identity:
            await websocket.close(code=1008)  # policy violation
            return
    await websocket.accept()
    ws_target_base = settings.bi_report_service_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
    query_str = str(websocket.query_params)
    target_ws_url = f"{ws_target_base}/ws/{path}" + (f"?{query_str}" if query_str else "")
    try:
        async with websockets.connect(target_ws_url) as backend_ws:
            async def client_to_backend():
                while True:
                    data = await websocket.receive_text()
                    await backend_ws.send(data)

            async def backend_to_client():
                async for data in backend_ws:
                    await websocket.send_text(data)

            await asyncio.gather(client_to_backend(), backend_to_client())
    except (WebSocketDisconnect, Exception):
        try:
            await websocket.close()
        except Exception:
            pass
