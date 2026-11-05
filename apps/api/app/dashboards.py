"""Dashboards: grade de tiles (texto, gráfico, KPI) com posição, e bloqueio otimista por versão (mesmo modelo dos relatórios)."""
import json
import uuid
from contextlib import closing
from datetime import datetime, timezone

from . import db
from .schemas import Dashboard, DashboardIn, DashboardUpdate


class DashboardError(ValueError):
    """Erro do pedido -> HTTP 4xx."""


class DashboardNotFound(DashboardError):
    pass


class DashboardConflict(DashboardError):
    """O dashboard foi alterado por outro cliente desde a versão que o chamador tinha."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row) -> Dashboard:
    return Dashboard(id=row["id"], title=row["title"], tiles=json.loads(row["tiles_json"]), version=row["version"],
                     created_at=row["created_at"], updated_at=row["updated_at"])


def _dump(d: DashboardIn) -> str:
    return json.dumps([t.model_dump(mode="json") for t in d.tiles], ensure_ascii=False)


def create_dashboard(d: DashboardIn) -> Dashboard:
    dash_id, now = uuid.uuid4().hex, _now()
    with closing(db.connect()) as con, con:
        con.execute("INSERT INTO dashboards VALUES (?,?,?,?,?,?)", [dash_id, d.title, _dump(d), 1, now, now])
    return get_dashboard(dash_id)


def get_dashboard(dash_id: str) -> Dashboard:
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM dashboards WHERE id = ?", [dash_id]).fetchone()
    if row is None:
        raise DashboardNotFound(f"dashboard not found: {dash_id}")
    return _row(row)


def list_dashboards() -> list[dict]:
    """Resumo (sem os tiles)."""
    with closing(db.connect()) as con:
        rows = con.execute("SELECT id, title, tiles_json, version, updated_at FROM dashboards ORDER BY updated_at DESC").fetchall()
    return [{"id": r["id"], "title": r["title"], "n_tiles": len(json.loads(r["tiles_json"])), "version": r["version"], "updated_at": r["updated_at"]} for r in rows]


def update_dashboard(dash_id: str, d: DashboardUpdate) -> Dashboard:
    """UPDATE condicional na versão: se outro cliente salvou antes, 0 linhas mudam e devolvemos conflito."""
    with closing(db.connect()) as con, con:
        changed = con.execute(
            "UPDATE dashboards SET title = ?, tiles_json = ?, version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
            [d.title, _dump(d), _now(), dash_id, d.version],
        ).rowcount
    if changed == 0:
        current = get_dashboard(dash_id)  # 404 se não existe
        raise DashboardConflict(f"dashboard was changed elsewhere (server version {current.version}, yours {d.version})")
    return get_dashboard(dash_id)


def delete_dashboard(dash_id: str) -> None:
    with closing(db.connect()) as con, con:
        if con.execute("DELETE FROM dashboards WHERE id = ?", [dash_id]).rowcount == 0:
            raise DashboardNotFound(f"dashboard not found: {dash_id}")
