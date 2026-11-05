from fastapi import APIRouter, HTTPException

from .. import reports
from ..schemas import Report, ReportIn, ReportUpdate

router = APIRouter(prefix="/reports", tags=["reports"])


def _http(exc: reports.ReportError) -> HTTPException:
    code = 404 if isinstance(exc, reports.ReportNotFound) else 409 if isinstance(exc, reports.ReportConflict) else 422
    return HTTPException(code, str(exc))


@router.post("", response_model=Report, status_code=201)
def create_report(rep: ReportIn) -> Report:
    return reports.create_report(rep)


@router.get("")
def list_reports() -> list[dict]:
    return reports.list_reports()


@router.get("/{report_id}", response_model=Report)
def get_report(report_id: str) -> Report:
    try:
        return reports.get_report(report_id)
    except reports.ReportError as exc:
        raise _http(exc) from exc


@router.put("/{report_id}", response_model=Report)
def update_report(report_id: str, rep: ReportUpdate) -> Report:
    """Salva o relatório inteiro. 409 se `version` não for a atual (alterado em outra aba)."""
    try:
        return reports.update_report(report_id, rep)
    except reports.ReportError as exc:
        raise _http(exc) from exc


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str) -> None:
    try:
        reports.delete_report(report_id)
    except reports.ReportError as exc:
        raise _http(exc) from exc
