import sqlite3
from pathlib import Path
from app.config import settings
from app import db


def test_tenants_table_created_and_default_seeded(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    con = db.connect()

    cur = con.execute("SELECT id, name, slug, tier FROM tenants WHERE id = 'default'")
    row = cur.fetchone()
    assert row is not None
    assert row["id"] == "default"
    assert row["name"] == "Default Organization"
    assert row["slug"] == "default"
    assert row["tier"] == "enterprise"

    con.close()


def test_tenant_id_columns_in_core_tables(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    con = db.connect()

    core_tables = ["datasets", "reports", "dashboards", "users", "collections"]
    for tbl in core_tables:
        cols = {r["name"] for r in con.execute(f"PRAGMA table_info({tbl})")}
        assert "tenant_id" in cols, f"Coluna tenant_id ausente na tabela {tbl}"

    con.close()


def test_multitenant_db_migration_from_legacy_schema(tmp_path: Path, monkeypatch):
    # Simula um banco meta.db antigo sem coluna tenant_id e sem tabela tenants
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "meta.db"
    legacy_con = sqlite3.connect(db_file)
    legacy_con.execute(
        """CREATE TABLE datasets (
             id TEXT PRIMARY KEY, name TEXT NOT NULL, table_name TEXT NOT NULL UNIQUE,
             n_rows INTEGER NOT NULL, columns_json TEXT NOT NULL, created_at TEXT NOT NULL)"""
    )
    legacy_con.execute(
        "INSERT INTO datasets VALUES ('ds1', 'My Dataset', 'my_table', 10, '[]', '2026-01-01T00:00:00')"
    )
    legacy_con.commit()
    legacy_con.close()

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    con = db.connect()

    # O dataset antigo deve ter tenant_id='default' por padrão
    cur = con.execute("SELECT id, tenant_id FROM datasets WHERE id = 'ds1'")
    row = cur.fetchone()
    assert row is not None
    assert row["tenant_id"] == "default"

    # Tabela tenants deve ter sido criada e ter o tenant default
    tenants_cur = con.execute("SELECT id FROM tenants")
    tenant_ids = [r["id"] for r in tenants_cur.fetchall()]
    assert "default" in tenant_ids

    con.close()
