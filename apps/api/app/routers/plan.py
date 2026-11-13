from fastapi import APIRouter, Depends, Request

from .. import plan_limits
from ..security import require_viewer

router = APIRouter(prefix="/plan", tags=["plan"], dependencies=[Depends(require_viewer)])


@router.get("/usage")
def usage(request: Request) -> dict:
    """Plano da organização ativa e o quanto dos limites já foi usado (datasets e armazenamento)."""
    return plan_limits.usage(plan_limits.current_plan(request))
