from fastapi import APIRouter, Depends, HTTPException

from .. import access, auth, reports
from ..schemas import MoveIn, Report, ReportIn, ReportUpdate

from ..security import can_modify, current_user, require_editor, require_viewer

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_viewer)])


def _http(exc: reports.ReportError) -> HTTPException:
    code = 404 if isinstance(exc, reports.ReportNotFound) else 409 if isinstance(exc, reports.ReportConflict) else 422
    return HTTPException(code, str(exc))


@router.post("", response_model=Report, status_code=201, dependencies=[Depends(require_editor)])
def create_report(rep: ReportIn, user: auth.User = Depends(current_user)) -> Report:
    created = reports.create_report(rep)
    access.claim("report", created.id, user)
    return access.annotate_one("report", created, user)


@router.get("")
def list_reports(user: auth.User = Depends(current_user)) -> list[dict]:
    return access.annotate("report", reports.list_reports(), user)


@router.get("/{report_id}", response_model=Report)
def get_report(report_id: str, user: auth.User = Depends(current_user)) -> Report:
    try:
        return access.annotate_one("report", reports.get_report(report_id), user)
    except reports.ReportError as exc:
        raise _http(exc) from exc


@router.put("/{report_id}", response_model=Report, dependencies=[Depends(can_modify("report", "report_id"))])
def update_report(report_id: str, rep: ReportUpdate, user: auth.User = Depends(current_user)) -> Report:
    """Salva o relatório inteiro. 409 se `version` não for a atual (alterado em outra aba)."""
    try:
        return access.annotate_one("report", reports.update_report(report_id, rep), user)
    except reports.ReportError as exc:
        raise _http(exc) from exc


@router.put("/{report_id}/collection", status_code=204, dependencies=[Depends(can_modify("report", "report_id"))])
def move_report(report_id: str, body: MoveIn) -> None:
    """Move para uma coleção (ou para a raiz). Não muda a versão: não conflita com quem está editando."""
    try:
        reports.get_report(report_id)
        access.set_collection("report", report_id, body.collection_id)
    except reports.ReportError as exc:
        raise _http(exc) from exc
    except access.CollectionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{report_id}", status_code=204, dependencies=[Depends(can_modify("report", "report_id"))])
def delete_report(report_id: str) -> None:
    try:
        reports.delete_report(report_id)
        access.forget("report", report_id)
    except reports.ReportError as exc:
        raise _http(exc) from exc
