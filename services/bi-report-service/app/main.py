from contextlib import asynccontextmanager
from typing import Optional
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import (
    BiReportError,
    DashboardConflict,
    DashboardNotFound,
    ReportConflict,
    ReportNotFound,
    SnapshotNotFound,
    create_dashboard,
    create_report,
    create_snapshot,
    delete_dashboard,
    delete_report,
    get_dashboard,
    get_report,
    init_db,
    list_dashboards,
    list_reports,
    list_snapshots,
    restore_snapshot,
    update_dashboard,
    update_report,
)
from app.schemas import (
    Dashboard,
    DashboardIn,
    DashboardUpdate,
    Report,
    ReportIn,
    ReportSnapshot,
    ReportUpdate,
)
from app.websocket_manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MetaStatistic BI & Report Service",
    version="0.1.0",
    description="Microservice for analytical reports, snapshots, BI dashboards and real-time collaboration",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_tenant_id(x_tenant_id: Optional[str] = Header(default=None)) -> str:
    if x_tenant_id and x_tenant_id.strip():
        return x_tenant_id.strip()
    return settings.default_tenant_id


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "bi-report-service",
        "version": "0.1.0",
    }


# ==========================================
# Rotas de Relatórios
# ==========================================

@app.get("/reports", response_model=list[Report])
def list_all_reports(x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    return list_reports(tenant_id)


@app.post("/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
def create_new_report(rep: ReportIn, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    return create_report(rep, tenant_id)


@app.get("/reports/{report_id}", response_model=Report)
def get_one_report(report_id: str, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return get_report(report_id, tenant_id)
    except ReportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.put("/reports/{report_id}", response_model=Report)
def update_existing_report(
    report_id: str,
    rep: ReportUpdate,
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return update_report(report_id, rep, tenant_id)
    except ReportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ReportConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@app.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_report(report_id: str, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        delete_report(report_id, tenant_id)
    except ReportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return None


# ==========================================
# Snapshots de Relatórios
# ==========================================

class SnapshotCreateRequest(BaseModel):
    note: str = ""


@app.post("/reports/{report_id}/snapshots", response_model=ReportSnapshot, status_code=status.HTTP_201_CREATED)
def create_report_snapshot(
    report_id: str,
    body: SnapshotCreateRequest = SnapshotCreateRequest(),
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return create_snapshot(report_id, tenant_id, note=body.note)
    except ReportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.get("/reports/{report_id}/snapshots", response_model=list[ReportSnapshot])
def get_report_snapshots(
    report_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return list_snapshots(report_id, tenant_id)
    except ReportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.post("/reports/{report_id}/snapshots/{snapshot_id}/restore", response_model=Report)
def restore_report_version(
    report_id: str,
    snapshot_id: str,
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return restore_snapshot(report_id, snapshot_id, tenant_id)
    except (ReportNotFound, SnapshotNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ==========================================
# Rotas de Dashboards
# ==========================================

@app.get("/dashboards", response_model=list[Dashboard])
def list_all_dashboards(x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    return list_dashboards(tenant_id)


@app.post("/dashboards", response_model=Dashboard, status_code=status.HTTP_201_CREATED)
def create_new_dashboard(dash: DashboardIn, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    return create_dashboard(dash, tenant_id)


@app.get("/dashboards/{dashboard_id}", response_model=Dashboard)
def get_one_dashboard(dashboard_id: str, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return get_dashboard(dashboard_id, tenant_id)
    except DashboardNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.put("/dashboards/{dashboard_id}", response_model=Dashboard)
def update_existing_dashboard(
    dashboard_id: str,
    dash: DashboardUpdate,
    x_tenant_id: Optional[str] = Header(default=None),
):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        return update_dashboard(dashboard_id, dash, tenant_id)
    except DashboardNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DashboardConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@app.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_dashboard(dashboard_id: str, x_tenant_id: Optional[str] = Header(default=None)):
    tenant_id = get_tenant_id(x_tenant_id)
    try:
        delete_dashboard(dashboard_id, tenant_id)
    except DashboardNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return None


# ==========================================
# WebSocket para Colaboração em Tempo Real
# ==========================================

@app.websocket("/ws/reports/{report_id}")
async def websocket_report_collaboration(
    websocket: WebSocket,
    report_id: str,
    user_id: str = Query(default="anonymous"),
    tenant_id: str = Query(default="default"),
):
    await ws_manager.connect(websocket, room_id=report_id, user_id=user_id, tenant_id=tenant_id)
    # Broadcast join event
    await ws_manager.broadcast(
        report_id,
        {
            "event": "USER_JOINED",
            "user_id": user_id,
            "room_id": report_id,
            "active_users": ws_manager.get_active_users(report_id),
        },
    )
    try:
        while True:
            data = await websocket.receive_json()
            # Encaminha a mutação ou mensagem para os outros participantes
            data["from_user"] = user_id
            await ws_manager.broadcast(report_id, data, exclude=websocket)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        await ws_manager.broadcast(
            report_id,
            {
                "event": "USER_LEFT",
                "user_id": user_id,
                "room_id": report_id,
                "active_users": ws_manager.get_active_users(report_id),
            },
        )
