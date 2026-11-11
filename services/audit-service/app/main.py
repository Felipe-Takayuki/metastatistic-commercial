from typing import List, Optional

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.audit_trail import (
    AuditEventCreate,
    AuditEventResponse,
    AuditExportResponse,
    AuditTrailManager,
    AuditVerificationResult,
)
from app.config import settings
from app.db import AuditDatabase

manager: Optional[AuditTrailManager] = None


def get_audit_manager() -> AuditTrailManager:
    global manager
    if manager is None:
        manager = AuditTrailManager(AuditDatabase(settings.database_url).get_connection)
    return manager


app = FastAPI(
    title="MetaStatistic Audit Service",
    version="1.0.0",
    description="Immutable SHA-256 hash-chained audit trail (SOC 2 Type II / FDA 21 CFR Part 11) for MetaStatistic",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "audit-service",
        "version": "1.0.0",
        "features": ["audit_trail_immutable", "hash_chain_sha256", "integrity_verification", "export"],
    }


@app.post("/audit/events", response_model=AuditEventResponse, status_code=status.HTTP_201_CREATED)
def record_audit_event(
    payload: AuditEventCreate,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    return audit.record_event(payload)


@app.get("/audit/events", response_model=List[AuditEventResponse])
def list_audit_events(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    return audit.list_events(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        limit=limit,
        offset=offset,
    )


@app.get("/audit/verify", response_model=AuditVerificationResult)
def verify_audit_trail(
    tenant_id: Optional[str] = None,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    """
    Executa a verificação matemática de integridade criptográfica da cadeia de hashes (Merkle/SHA-256).
    Comprova que não houve nenhuma adulteração no banco de dados.
    """
    return audit.verify_integrity(tenant_id=tenant_id)


@app.get("/audit/export", response_model=AuditExportResponse)
def export_audit_trail(
    tenant_id: Optional[str] = None,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    """
    Exporta a trilha de auditoria completa com atestado de integridade e metadados de conformidade.
    """
    return audit.export_audit_trail(tenant_id=tenant_id)
