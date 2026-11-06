"""Conexão SQLite compartilhada (metadados de datasets, relatórios e dashboards). Uma conexão por operação."""
from datetime import datetime, timezone
import sqlite3

from .config import settings

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS tenants (
         id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
         tier TEXT NOT NULL, created_at TEXT NOT NULL)""",
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
    # dono e coleção ficam à parte dos recursos: um recurso SEM linha aqui é "legado" (sem dono, na raiz)
    """CREATE TABLE IF NOT EXISTS resources (
         kind TEXT NOT NULL, id TEXT NOT NULL, owner_id TEXT, collection_id TEXT,
         PRIMARY KEY (kind, id))""",
    """CREATE TABLE IF NOT EXISTS collections (
         id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id TEXT, created_at TEXT NOT NULL)""",
    # leitura por dataset: sem linha em dataset_acl = aberto a todos que entraram
    """CREATE TABLE IF NOT EXISTS dataset_acl (dataset_id TEXT PRIMARY KEY, restricted INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS dataset_grants (dataset_id TEXT NOT NULL, user_id TEXT NOT NULL, PRIMARY KEY (dataset_id, user_id))""",
    # segurança por linha: a coluna do dataset é comparada com o atributo do usuário
    """CREATE TABLE IF NOT EXISTS dataset_rls (dataset_id TEXT PRIMARY KEY, column_name TEXT NOT NULL, attribute TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS user_attributes (user_id TEXT NOT NULL, name TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (user_id, name))""",
    """CREATE TABLE IF NOT EXISTS rls_views (view_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL)""",
    # de que receita (passos sobre qual dataset) cada dataset derivado saiu
    """CREATE TABLE IF NOT EXISTS dataset_recipes (
         dataset_id TEXT PRIMARY KEY, recipe_json TEXT NOT NULL, sql TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS audit (
         id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id TEXT, username TEXT,
         action TEXT NOT NULL, kind TEXT, target TEXT, detail TEXT)""",
)


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "datasets").mkdir(exist_ok=True)
    con = sqlite3.connect(settings.data_dir / "meta.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    for ddl in _SCHEMA:
        con.execute(ddl)

    # Inserção do tenant padrão caso não exista
    cur = con.execute("SELECT id FROM tenants WHERE id = 'default'")
    if not cur.fetchone():
        now = datetime.now(timezone.utc).isoformat()
        con.execute(
            "INSERT INTO tenants (id, name, slug, tier, created_at) VALUES (?, ?, ?, ?, ?)",
            ("default", "Default Organization", "default", "enterprise", now),
        )
        con.commit()

    # Migração multi-tenant: garante que coluna tenant_id existe nas tabelas principais
    tables_to_migrate = ["datasets", "reports", "dashboards", "users", "collections"]
    for tbl in tables_to_migrate:
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({tbl})")}
        if cols and "tenant_id" not in cols:
            con.execute(f"ALTER TABLE {tbl} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")

    # migração: dashboards criados antes dos filtros não têm a coluna
    if "filters_json" not in {r["name"] for r in con.execute("PRAGMA table_info(dashboards)")}:
        con.execute("ALTER TABLE dashboards ADD COLUMN filters_json TEXT NOT NULL DEFAULT '[]'")
    if "last_seen" not in {r["name"] for r in con.execute("PRAGMA table_info(sessions)")}:
        con.execute("ALTER TABLE sessions ADD COLUMN last_seen TEXT")
    return con

