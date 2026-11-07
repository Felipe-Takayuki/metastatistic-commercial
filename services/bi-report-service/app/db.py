import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings
from app.schemas import (
    Dashboard,
    DashboardIn,
    DashboardTile,
    DashboardUpdate,
    Report,
    ReportBlock,
    ReportIn,
    ReportSnapshot,
    ReportUpdate,
)


class BiReportError(Exception):
    """Exceção base de regras de negócio de BI e relatórios."""


class ReportNotFound(BiReportError):
    """Relatório não encontrado para o tenant."""


class ReportConflict(BiReportError):
    """Conflito de versão (bloqueio otimista violado)."""


class SnapshotNotFound(BiReportError):
    """Snapshot não encontrado."""


class DashboardNotFound(BiReportError):
    """Dashboard não encontrado para o tenant."""


class DashboardConflict(BiReportError):
    """Conflito de versão no dashboard."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db_path() -> Path:
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        path_str = db_url.replace("sqlite:///", "")
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(settings.data_dir) / "bi_reports.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_connection() -> sqlite3.Connection:
    path = _get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Inicializa esquemas e tabelas de dados."""
    with closing(get_connection()) as conn, conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            title TEXT NOT NULL,
            blocks_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_tenant ON reports(tenant_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS report_snapshots (
            id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            title TEXT NOT NULL,
            blocks_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_report ON report_snapshots(report_id, tenant_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS dashboards (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            title TEXT NOT NULL,
            tiles_json TEXT NOT NULL,
            filters_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dashboards_tenant ON dashboards(tenant_id, updated_at DESC);
        """)


def _row_to_report(row: sqlite3.Row) -> Report:
    raw_blocks = json.loads(row["blocks_json"])
    blocks = [ReportBlock(**b) for b in raw_blocks]
    return Report(
        id=row["id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        blocks=blocks,
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_snapshot(row: sqlite3.Row) -> ReportSnapshot:
    raw_blocks = json.loads(row["blocks_json"])
    blocks = [ReportBlock(**b) for b in raw_blocks]
    return ReportSnapshot(
        id=row["id"],
        report_id=row["report_id"],
        tenant_id=row["tenant_id"],
        version=row["version"],
        title=row["title"],
        blocks=blocks,
        created_at=row["created_at"],
        note=row["note"] if "note" in row.keys() else "",
    )


def _row_to_dashboard(row: sqlite3.Row) -> Dashboard:
    tiles = [DashboardTile(**t) for t in json.loads(row["tiles_json"])]
    filters = json.loads(row["filters_json"])
    return Dashboard(
        id=row["id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        tiles=tiles,
        filters=filters,
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# --- Relatórios ---

def create_report(rep: ReportIn, tenant_id: str) -> Report:
    report_id = uuid.uuid4().hex
    now = _now()
    blocks_json = json.dumps([b.model_dump(mode="json") for b in rep.blocks], ensure_ascii=False)
    with closing(get_connection()) as conn, conn:
        conn.execute(
            """
            INSERT INTO reports (id, tenant_id, title, blocks_json, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (report_id, tenant_id, rep.title, blocks_json, now, now),
        )
    return get_report(report_id, tenant_id)


def get_report(report_id: str, tenant_id: str) -> Report:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND tenant_id = ?",
            (report_id, tenant_id),
        ).fetchone()
    if not row:
        raise ReportNotFound(f"Report not found: {report_id} for tenant: {tenant_id}")
    return _row_to_report(row)


def list_reports(tenant_id: str) -> list[Report]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE tenant_id = ? ORDER BY updated_at DESC",
            (tenant_id,),
        ).fetchall()
    return [_row_to_report(r) for r in rows]


def update_report(report_id: str, rep: ReportUpdate, tenant_id: str) -> Report:
    """Atualiza o relatório com bloqueio otimista de versão."""
    now = _now()
    blocks_json = json.dumps([b.model_dump(mode="json") for b in rep.blocks], ensure_ascii=False)
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute(
            """
            UPDATE reports
            SET title = ?, blocks_json = ?, version = version + 1, updated_at = ?
            WHERE id = ? AND tenant_id = ? AND version = ?
            """,
            (rep.title, blocks_json, now, report_id, tenant_id, rep.version),
        )
        if cursor.rowcount == 0:
            # Verifica se o relatório existe para determinar se é 404 ou 409
            existing = conn.execute(
                "SELECT version FROM reports WHERE id = ? AND tenant_id = ?",
                (report_id, tenant_id),
            ).fetchone()
            if not existing:
                raise ReportNotFound(f"Report not found: {report_id} for tenant: {tenant_id}")
            raise ReportConflict(
                f"Conflict: server version is {existing['version']}, but payload requested update for version {rep.version}"
            )
    return get_report(report_id, tenant_id)


def delete_report(report_id: str, tenant_id: str) -> None:
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute(
            "DELETE FROM reports WHERE id = ? AND tenant_id = ?",
            (report_id, tenant_id),
        )
        if cursor.rowcount == 0:
            raise ReportNotFound(f"Report not found: {report_id} for tenant: {tenant_id}")


# --- Snapshots de Relatórios ---

def create_snapshot(report_id: str, tenant_id: str, note: str = "") -> ReportSnapshot:
    report = get_report(report_id, tenant_id)
    snapshot_id = uuid.uuid4().hex
    now = _now()
    blocks_json = json.dumps([b.model_dump(mode="json") for b in report.blocks], ensure_ascii=False)
    with closing(get_connection()) as conn, conn:
        conn.execute(
            """
            INSERT INTO report_snapshots (id, report_id, tenant_id, version, title, blocks_json, created_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (snapshot_id, report.id, tenant_id, report.version, report.title, blocks_json, now, note),
        )
        row = conn.execute(
            "SELECT * FROM report_snapshots WHERE id = ? AND tenant_id = ?",
            (snapshot_id, tenant_id),
        ).fetchone()
    return _row_to_snapshot(row)


def list_snapshots(report_id: str, tenant_id: str) -> list[ReportSnapshot]:
    # Valida existência do report
    get_report(report_id, tenant_id)
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM report_snapshots WHERE report_id = ? AND tenant_id = ? ORDER BY created_at DESC",
            (report_id, tenant_id),
        ).fetchall()
    return [_row_to_snapshot(r) for r in rows]


def restore_snapshot(report_id: str, snapshot_id: str, tenant_id: str) -> Report:
    """Restaura o conteúdo de um snapshot, incrementando a versão do relatório atual."""
    current = get_report(report_id, tenant_id)
    with closing(get_connection()) as conn:
        snap_row = conn.execute(
            "SELECT * FROM report_snapshots WHERE id = ? AND report_id = ? AND tenant_id = ?",
            (snapshot_id, report_id, tenant_id),
        ).fetchone()
        if not snap_row:
            raise SnapshotNotFound(f"Snapshot not found: {snapshot_id}")

    snapshot = _row_to_snapshot(snap_row)
    update_req = ReportUpdate(
        title=snapshot.title,
        blocks=snapshot.blocks,
        version=current.version,
    )
    return update_report(report_id, update_req, tenant_id)


# --- Dashboards ---

def create_dashboard(dash: DashboardIn, tenant_id: str) -> Dashboard:
    dash_id = uuid.uuid4().hex
    now = _now()
    tiles_json = json.dumps([t.model_dump(mode="json") for t in dash.tiles], ensure_ascii=False)
    filters_json = json.dumps(dash.filters, ensure_ascii=False)
    with closing(get_connection()) as conn, conn:
        conn.execute(
            """
            INSERT INTO dashboards (id, tenant_id, title, tiles_json, filters_json, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (dash_id, tenant_id, dash.title, tiles_json, filters_json, now, now),
        )
    return get_dashboard(dash_id, tenant_id)


def get_dashboard(dash_id: str, tenant_id: str) -> Dashboard:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT * FROM dashboards WHERE id = ? AND tenant_id = ?",
            (dash_id, tenant_id),
        ).fetchone()
    if not row:
        raise DashboardNotFound(f"Dashboard not found: {dash_id} for tenant: {tenant_id}")
    return _row_to_dashboard(row)


def list_dashboards(tenant_id: str) -> list[Dashboard]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT * FROM dashboards WHERE tenant_id = ? ORDER BY updated_at DESC",
            (tenant_id,),
        ).fetchall()
    return [_row_to_dashboard(r) for r in rows]


def update_dashboard(dash_id: str, dash: DashboardUpdate, tenant_id: str) -> Dashboard:
    now = _now()
    tiles_json = json.dumps([t.model_dump(mode="json") for t in dash.tiles], ensure_ascii=False)
    filters_json = json.dumps(dash.filters, ensure_ascii=False)
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute(
            """
            UPDATE dashboards
            SET title = ?, tiles_json = ?, filters_json = ?, version = version + 1, updated_at = ?
            WHERE id = ? AND tenant_id = ? AND version = ?
            """,
            (dash.title, tiles_json, filters_json, now, dash_id, tenant_id, dash.version),
        )
        if cursor.rowcount == 0:
            existing = conn.execute(
                "SELECT version FROM dashboards WHERE id = ? AND tenant_id = ?",
                (dash_id, tenant_id),
            ).fetchone()
            if not existing:
                raise DashboardNotFound(f"Dashboard not found: {dash_id} for tenant: {tenant_id}")
            raise DashboardConflict(
                f"Conflict: server version is {existing['version']}, but payload requested update for version {dash.version}"
            )
    return get_dashboard(dash_id, tenant_id)


def delete_dashboard(dash_id: str, tenant_id: str) -> None:
    with closing(get_connection()) as conn, conn:
        cursor = conn.execute(
            "DELETE FROM dashboards WHERE id = ? AND tenant_id = ?",
            (dash_id, tenant_id),
        )
        if cursor.rowcount == 0:
            raise DashboardNotFound(f"Dashboard not found: {dash_id} for tenant: {tenant_id}")
