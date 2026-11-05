from fastapi import APIRouter, HTTPException

from .. import dashboards
from ..schemas import Dashboard, DashboardIn, DashboardUpdate

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _http(exc: dashboards.DashboardError) -> HTTPException:
    code = 404 if isinstance(exc, dashboards.DashboardNotFound) else 409 if isinstance(exc, dashboards.DashboardConflict) else 422
    return HTTPException(code, str(exc))


@router.post("", response_model=Dashboard, status_code=201)
def create_dashboard(d: DashboardIn) -> Dashboard:
    return dashboards.create_dashboard(d)


@router.get("")
def list_dashboards() -> list[dict]:
    return dashboards.list_dashboards()


@router.get("/{dash_id}", response_model=Dashboard)
def get_dashboard(dash_id: str) -> Dashboard:
    try:
        return dashboards.get_dashboard(dash_id)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc


@router.put("/{dash_id}", response_model=Dashboard)
def update_dashboard(dash_id: str, d: DashboardUpdate) -> Dashboard:
    """Salva o dashboard inteiro. 409 se `version` não for a atual (alterado em outra aba)."""
    try:
        return dashboards.update_dashboard(dash_id, d)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc


@router.delete("/{dash_id}", status_code=204)
def delete_dashboard(dash_id: str) -> None:
    try:
        dashboards.delete_dashboard(dash_id)
    except dashboards.DashboardError as exc:
        raise _http(exc) from exc
