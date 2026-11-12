"""Importa a trilha de auditoria que vivia na tabela `audit_log` do auth-tenant-service.

Uso:  python -m audit_service.import_legacy /caminho/auth_tenant.db

Copia as linhas preservando id, event_id, timestamp e hashes (a cadeia SHA-256 não depende do id), então
`GET /audit/verify` continua válido após a migração. Idempotente: eventos já existentes (mesmo event_id) são ignorados.
A tabela original no auth-tenant-service NÃO é alterada.
"""
import sqlite3
import sys

from audit_service.audit_trail import AuditTrailManager
from audit_service.config import settings
from audit_service.db import AuditDatabase

COLUMNS = (
    "id, event_id, tenant_id, user_id, action, resource_type, resource_id, "
    "details, ip_address, user_agent, timestamp, prev_hash, record_hash"
)


def import_legacy(source_db_path: str, target_db_url: str) -> int:
    target = AuditDatabase(target_db_url)
    AuditTrailManager(target.get_connection)  # garante o schema

    src = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    try:
        rows = src.execute(f"SELECT {COLUMNS} FROM audit_log ORDER BY id ASC").fetchall()
    finally:
        src.close()

    conn = target.get_connection()
    try:
        before = conn.total_changes
        conn.executemany(f"INSERT OR IGNORE INTO audit_log ({COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        return conn.total_changes - before
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python -m audit_service.import_legacy <caminho do auth_tenant.db>")
    print(f"{import_legacy(sys.argv[1], settings.database_url)} evento(s) importado(s)")
