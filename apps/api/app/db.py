"""Conexão SQLite compartilhada (metadados de datasets, relatórios e dashboards). Uma conexão por operação."""
import sqlite3

from .config import settings

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS datasets (
         id TEXT PRIMARY KEY, name TEXT NOT NULL, table_name TEXT NOT NULL UNIQUE,
         n_rows INTEGER NOT NULL, columns_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS reports (
         id TEXT PRIMARY KEY, title TEXT NOT NULL, blocks_json TEXT NOT NULL,
         version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS dashboards (
         id TEXT PRIMARY KEY, title TEXT NOT NULL, tiles_json TEXT NOT NULL,
         version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS users (
         id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
         password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
         created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS sessions (
         token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
         created_at TEXT NOT NULL, expires_at TEXT NOT NULL)""",
)


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "datasets").mkdir(exist_ok=True)
    con = sqlite3.connect(settings.data_dir / "meta.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    for ddl in _SCHEMA:
        con.execute(ddl)
    # migração: dashboards criados antes dos filtros não têm a coluna
    if "filters_json" not in {r["name"] for r in con.execute("PRAGMA table_info(dashboards)")}:
        con.execute("ALTER TABLE dashboards ADD COLUMN filters_json TEXT NOT NULL DEFAULT '[]'")
    return con
