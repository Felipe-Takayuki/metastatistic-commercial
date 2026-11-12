import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

GENESIS_HASH = "0" * 64


class AuditEventCreate(BaseModel):
    tenant_id: str
    user_id: str
    action: str = Field(..., description="Action name, e.g., auth.login, dataset.create, analysis.run")
    resource_type: str = Field(..., description="Target resource type, e.g., dataset, model, report")
    resource_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditEventResponse(BaseModel):
    id: int
    event_id: str
    tenant_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: str
    prev_hash: str
    record_hash: str


class AuditVerificationResult(BaseModel):
    valid: bool
    total_records: int
    latest_hash: Optional[str] = None
    genesis_hash: str = GENESIS_HASH
    tampered_at_id: Optional[int] = None
    tampered_event_id: Optional[str] = None
    reason: Optional[str] = None
    verified_at: str


class AuditExportResponse(BaseModel):
    tenant_id: Optional[str] = None
    export_timestamp: str
    total_events: int
    compliance_standard: str = "SOC 2 Type II / FDA 21 CFR Part 11"
    integrity_verified: bool
    latest_hash: Optional[str] = None
    events: List[AuditEventResponse]


def compute_record_hash(
    tenant_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    details_json: str,
    timestamp: str,
    prev_hash: str,
) -> str:
    """
    Calcula hash SHA-256 canônico e determinístico para o evento de auditoria.
    Garante encadeamento criptográfico inviolável.
    """
    canonical_string = (
        f"tenant:{tenant_id}|user:{user_id}|action:{action}|"
        f"resource_type:{resource_type}|resource_id:{resource_id or ''}|"
        f"details:{details_json}|timestamp:{timestamp}|prev_hash:{prev_hash}"
    )
    return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()


class AuditTrailManager:
    def __init__(self, db_connection_provider):
        self._get_connection = db_connection_provider
        self._init_table()

    def _init_table(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    details TEXT DEFAULT '{}',
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_log(tenant_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
            """)

    def record_event(self, event: AuditEventCreate) -> AuditEventResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid.uuid4())
        details_json = json.dumps(event.details, sort_keys=True)

        with self._get_connection() as conn:
            # Obtém o último hash registrado para o tenant (ou global se preferir consistência por tenant)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT record_hash FROM audit_log 
                WHERE tenant_id = ? 
                ORDER BY id DESC LIMIT 1
                """,
                (event.tenant_id,),
            )
            row = cursor.fetchone()
            prev_hash = row["record_hash"] if row else GENESIS_HASH

            record_hash = compute_record_hash(
                tenant_id=event.tenant_id,
                user_id=event.user_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                details_json=details_json,
                timestamp=now_iso,
                prev_hash=prev_hash,
            )

            cursor.execute(
                """
                INSERT INTO audit_log (
                    event_id, tenant_id, user_id, action, resource_type, resource_id,
                    details, ip_address, user_agent, timestamp, prev_hash, record_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.tenant_id,
                    event.user_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    details_json,
                    event.ip_address,
                    event.user_agent,
                    now_iso,
                    prev_hash,
                    record_hash,
                ),
            )
            rec_id = cursor.lastrowid
            conn.commit()

        return AuditEventResponse(
            id=rec_id,
            event_id=event_id,
            tenant_id=event.tenant_id,
            user_id=event.user_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=event.details,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            timestamp=now_iso,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )

    def list_events(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEventResponse]:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params: list = []

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if action:
            query += " AND action = ?"
            params.append(action)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                try:
                    dt = json.loads(r["details"]) if r["details"] else {}
                except Exception:
                    dt = {}
                results.append(
                    AuditEventResponse(
                        id=r["id"],
                        event_id=r["event_id"],
                        tenant_id=r["tenant_id"],
                        user_id=r["user_id"],
                        action=r["action"],
                        resource_type=r["resource_type"],
                        resource_id=r["resource_id"],
                        details=dt,
                        ip_address=r["ip_address"],
                        user_agent=r["user_agent"],
                        timestamp=r["timestamp"],
                        prev_hash=r["prev_hash"],
                        record_hash=r["record_hash"],
                    )
                )
            return results

    def verify_integrity(self, tenant_id: Optional[str] = None) -> AuditVerificationResult:
        """
        Verifica a cadeia criptográfica de hashes em ordem sequencial.
        Detecta qualquer adulteração física ou lógica no banco de dados.

        A cadeia é por tenant (ver `record_event`): com `tenant_id` verifica só a cadeia dele; sem `tenant_id`
        verifica a cadeia de cada tenant separadamente e reporta o primeiro registro adulterado encontrado.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        query = "SELECT * FROM audit_log"
        params = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY id ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        chains: Dict[str, list] = {}
        for row in rows:
            chains.setdefault(row["tenant_id"], []).append(row)

        for chain in chains.values():
            failure = self._find_chain_failure(chain)
            if failure:
                rec_id, event_id, reason = failure
                return AuditVerificationResult(
                    valid=False,
                    total_records=len(rows),
                    latest_hash=None,
                    genesis_hash=GENESIS_HASH,
                    tampered_at_id=rec_id,
                    tampered_event_id=event_id,
                    reason=reason,
                    verified_at=now_iso,
                )

        return AuditVerificationResult(
            valid=True,
            total_records=len(rows),
            latest_hash=rows[-1]["record_hash"] if rows else None,  # hash do último evento gravado
            genesis_hash=GENESIS_HASH,
            verified_at=now_iso,
        )

    @staticmethod
    def _find_chain_failure(chain: list) -> Optional[tuple]:
        """Retorna (id, event_id, motivo) do primeiro registro inválido de uma cadeia, ou None se íntegra."""
        expected_prev_hash = GENESIS_HASH
        for row in chain:
            # 1. Valida encadeamento com o registro anterior
            if row["prev_hash"] != expected_prev_hash:
                return (
                    row["id"],
                    row["event_id"],
                    f"Broken hash chain: expected prev_hash '{expected_prev_hash}', got '{row['prev_hash']}'",
                )

            # 2. Recalcula hash dos dados para comprovar integridade do registro
            recalculated_hash = compute_record_hash(
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                details_json=row["details"] or "{}",
                timestamp=row["timestamp"],
                prev_hash=row["prev_hash"],
            )
            if recalculated_hash != row["record_hash"]:
                return (
                    row["id"],
                    row["event_id"],
                    f"Content tampering detected: payload hash mismatch on record {row['id']}",
                )

            expected_prev_hash = row["record_hash"]
        return None

    def export_audit_trail(self, tenant_id: Optional[str] = None) -> AuditExportResponse:
        verification = self.verify_integrity(tenant_id)
        events = self.list_events(tenant_id=tenant_id, limit=100000)
        # Reordena para export cronológico asc
        events.reverse()

        return AuditExportResponse(
            tenant_id=tenant_id,
            export_timestamp=datetime.now(timezone.utc).isoformat(),
            total_events=len(events),
            compliance_standard="SOC 2 Type II / FDA 21 CFR Part 11",
            integrity_verified=verification.valid,
            latest_hash=verification.latest_hash,
            events=events,
        )
