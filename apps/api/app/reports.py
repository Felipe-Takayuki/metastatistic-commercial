"""Relatórios: documentos compostos por blocos (texto, gráfico, análise), com bloqueio otimista por versão."""
import json
import uuid
from contextlib import closing
from datetime import datetime, timezone

from . import db
from .schemas import Report, ReportIn, ReportUpdate


class ReportError(ValueError):
    """Erro do pedido -> HTTP 4xx."""


class ReportNotFound(ReportError):
    pass


class ReportConflict(ReportError):
    """O relatório foi alterado por outro cliente desde a versão que o chamador tinha."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_report(row) -> Report:
    return Report(
        id=row["id"], title=row["title"], blocks=json.loads(row["blocks_json"]), version=row["version"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _dump_blocks(rep: ReportIn) -> str:
    return json.dumps([b.model_dump(mode="json") for b in rep.blocks], ensure_ascii=False)


def create_report(rep: ReportIn) -> Report:
    report_id, now = uuid.uuid4().hex, _now()
    with closing(db.connect()) as con, con:
        con.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)", [report_id, rep.title, _dump_blocks(rep), 1, now, now])
    return get_report(report_id)


def get_report(report_id: str) -> Report:
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM reports WHERE id = ?", [report_id]).fetchone()
    if row is None:
        raise ReportNotFound(f"report not found: {report_id}")
    return _row_to_report(row)


def list_reports() -> list[dict]:
    """Resumo (sem os blocos): a lista não precisa carregar o conteúdo de todos os relatórios."""
    with closing(db.connect()) as con:
        rows = con.execute("SELECT id, title, blocks_json, version, updated_at FROM reports ORDER BY updated_at DESC").fetchall()
    return [
        {"id": r["id"], "title": r["title"], "n_blocks": len(json.loads(r["blocks_json"])), "version": r["version"], "updated_at": r["updated_at"]}
        for r in rows
    ]


def update_report(report_id: str, rep: ReportUpdate) -> Report:
    """UPDATE condicional na versão: se outro cliente salvou antes, 0 linhas mudam e devolvemos conflito."""
    with closing(db.connect()) as con, con:
        cur = con.execute(
            "UPDATE reports SET title = ?, blocks_json = ?, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
            [rep.title, _dump_blocks(rep), _now(), report_id, rep.version],
        )
        changed = cur.rowcount
    if changed == 0:
        current = get_report(report_id)  # 404 se não existe
        raise ReportConflict(f"report was changed elsewhere (server version {current.version}, yours {rep.version})")
    return get_report(report_id)


def delete_report(report_id: str) -> None:
    with closing(db.connect()) as con, con:
        cur = con.execute("DELETE FROM reports WHERE id = ?", [report_id])
        if cur.rowcount == 0:
            raise ReportNotFound(f"report not found: {report_id}")
