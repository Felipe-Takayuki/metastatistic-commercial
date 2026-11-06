from fastapi import APIRouter, Depends, HTTPException

from .. import access, audit, auth, dashboards
from ..schemas import Dashboard, DashboardIn, DashboardUpdate, MoveIn
from ..security import can_modify, current_user, require_editor, require_viewer

router = APIRouter(prefix="/dashboards", tags=["dashboards"], dependencies=[Depends(require_viewer)])


def _http(exc: dashboards.DashboardError) -> HTTPException:
    code = 404 if isinstance(exc, dashboards.DashboardNotFound) else 409 if isinstance(exc, dashboards.DashboardConflict) else 422
    return HTTPException(code, str(exc))


@router.post("", response_model=Dashboard, status_code=201, dependencies=[Depends(require_editor)])
def create_dashboard(d: DashboardIn, user: auth.User = Depends(current_user)) -> Dashboard:
    created = dashboards.create_dashboard(d)
    access.claim("dashboard", created.id, user)
    audit.log(user, "create", "dashboard", created.id, created.title)
    return access.annotate_one("dashboard", created, user)


@router.get("")
def list_dashboards(user: auth.User = Depends(current_user)) -> list[dict]:
    return access.annotate("dashboard", dashboards.list_dashboards(), user)


@router.get("/{dash_id}", response_model=Dashboard)
def get_dashboard(dash_id: str, user: auth.User = Depends(current_user)) -> Dashboard:
    try:
        return access.annotate_one("dashboard", dashboards.get_dashboard(dash_id), user)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc


@router.put("/{dash_id}", response_model=Dashboard, dependencies=[Depends(can_modify("dashboard", "dash_id"))])
def update_dashboard(dash_id: str, d: DashboardUpdate, user: auth.User = Depends(current_user)) -> Dashboard:
    """Salva o dashboard inteiro. 409 se `version` não for a atual (alterado em outra aba)."""
    try:
        return access.annotate_one("dashboard", dashboards.update_dashboard(dash_id, d), user)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc


@router.put("/{dash_id}/collection", status_code=204, dependencies=[Depends(can_modify("dashboard", "dash_id"))])
def move_dashboard(dash_id: str, body: MoveIn, user: auth.User = Depends(current_user)) -> None:
    try:
        dashboards.get_dashboard(dash_id)
        access.set_collection("dashboard", dash_id, body.collection_id)
        audit.log(user, "move", "dashboard", dash_id, body.collection_id or "raiz")
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc
    except access.CollectionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{dash_id}", status_code=204, dependencies=[Depends(can_modify("dashboard", "dash_id"))])
def delete_dashboard(dash_id: str, user: auth.User = Depends(current_user)) -> None:
    try:
        title = dashboards.get_dashboard(dash_id).title
        dashboards.delete_dashboard(dash_id)
        access.forget("dashboard", dash_id)
        audit.log(user, "delete", "dashboard", dash_id, title)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc
