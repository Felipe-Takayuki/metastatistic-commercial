"""Cliente HTTP do audit-service.

A trilha de auditoria vive no audit-service. Este cliente apenas envia os eventos; falha ao enviar é registrada em log
e NÃO derruba a operação principal (mesma política best-effort do log de auditoria do apps/api).
"""
import logging
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class AuditEventCreate(BaseModel):
    tenant_id: str
    user_id: str
    action: str = Field(..., description="Action name, e.g., auth.login, dataset.create, analysis.run")
    resource_type: str = Field(..., description="Target resource type, e.g., dataset, model, report")
    resource_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditClient:
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def record_event(self, event: AuditEventCreate) -> None:
        if not self.base_url:
            return
        try:
            resp = httpx.post(
                f"{self.base_url}/audit/events",
                json=event.model_dump(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as exc:  # auditoria é best-effort
            logger.error("Failed to record audit event %s for tenant %s: %s", event.action, event.tenant_id, exc)


def get_audit_manager() -> AuditClient:
    return AuditClient(settings.audit_service_url)
