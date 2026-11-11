import sqlite3
from pathlib import Path


class AuditDatabase:
    """Provedor de conexões SQLite do audit-service (banco próprio, separado do auth-tenant-service)."""

    def __init__(self, database_url: str = "sqlite:///./audit.db"):
        if database_url.startswith("sqlite:///"):
            self.db_path = database_url.replace("sqlite:///", "", 1)
        elif database_url.startswith("sqlite://"):
            self.db_path = database_url.replace("sqlite://", "", 1)
        else:
            self.db_path = database_url

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
