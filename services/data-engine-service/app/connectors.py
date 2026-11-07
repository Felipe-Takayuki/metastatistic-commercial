import sqlite3
import time
import socket
from typing import Dict, List, Optional
import duckdb

from app.schemas import ConnectionConfig, ConnectionTestResponse


class ConnectionManager:
    def __init__(self):
        # tenant_id -> {conn_id: ConnectionConfig}
        self._connections: Dict[str, Dict[str, ConnectionConfig]] = {}

    def register_connection(self, config: ConnectionConfig) -> ConnectionConfig:
        tenant_conns = self._connections.setdefault(config.tenant_id, {})
        tenant_conns[config.id] = config
        return config

    def list_connections(self, tenant_id: str) -> List[ConnectionConfig]:
        return list(self._connections.get(tenant_id, {}).values())

    def get_connection(self, tenant_id: str, conn_id: str) -> Optional[ConnectionConfig]:
        return self._connections.get(tenant_id, {}).get(conn_id)

    def delete_connection(self, tenant_id: str, conn_id: str) -> bool:
        if tenant_id in self._connections and conn_id in self._connections[tenant_id]:
            del self._connections[tenant_id][conn_id]
            return True
        return False

    def test_connection(self, config: ConnectionConfig) -> ConnectionTestResponse:
        start_time = time.perf_counter()
        c_type = config.type.lower()

        try:
            if c_type == "sqlite":
                target = config.path or config.database or ":memory:"
                conn = sqlite3.connect(target, timeout=2.0)
                cur = conn.cursor()
                cur.execute("SELECT 1;")
                cur.fetchone()
                conn.close()
                latency = (time.perf_counter() - start_time) * 1000.0
                return ConnectionTestResponse(
                    success=True,
                    message=f"Successfully connected to SQLite database ({target})",
                    latency_ms=round(latency, 2),
                )

            elif c_type == "duckdb":
                target = config.path or config.database or ":memory:"
                con = duckdb.connect(target)
                con.execute("SELECT 1;")
                con.close()
                latency = (time.perf_counter() - start_time) * 1000.0
                return ConnectionTestResponse(
                    success=True,
                    message=f"Successfully connected to DuckDB instance ({target})",
                    latency_ms=round(latency, 2),
                )

            elif c_type in ("postgres", "mysql"):
                # Validação de conectividade de rede com timeout seguro de 2 segundos
                if not config.host:
                    return ConnectionTestResponse(
                        success=False,
                        message=f"Missing host for {c_type.upper()} connection",
                    )
                port = config.port or (5432 if c_type == "postgres" else 3306)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                try:
                    sock.connect((config.host, port))
                    sock.close()
                    latency = (time.perf_counter() - start_time) * 1000.0
                    return ConnectionTestResponse(
                        success=True,
                        message=f"Successfully established TCP handshake with {c_type.upper()} at {config.host}:{port}",
                        latency_ms=round(latency, 2),
                    )
                except Exception as net_err:
                    sock.close()
                    return ConnectionTestResponse(
                        success=False,
                        message=f"Failed to connect to {config.host}:{port}: {str(net_err)}",
                    )

            else:
                return ConnectionTestResponse(
                    success=False,
                    message=f"Unsupported connection type: {config.type}",
                )

        except Exception as exc:
            latency = (time.perf_counter() - start_time) * 1000.0
            return ConnectionTestResponse(
                success=False,
                message=f"Connection test failed: {str(exc)}",
                latency_ms=round(latency, 2),
            )


manager = ConnectionManager()
