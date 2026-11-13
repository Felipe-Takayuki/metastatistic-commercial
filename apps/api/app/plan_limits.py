"""Limites do plano (Free / Pro) aplicados na API.

Quem diz o plano é o gateway: ele confere no auth-tenant-service se o usuário é membro do tenant pedido e repassa o plano
e as cotas verificados em `X-Tenant-Tier` e `X-Tenant-Quotas` (o cliente não consegue forjá-los: o gateway descarta os
que vierem de fora). Sem esses cabeçalhos — workspace padrão, não membro, ou chamada que não passou pelo gateway — valem
os limites do Free. Com a autenticação desligada (demonstração local) não há limite.

Estouro de limite => HTTP 402 com uma mensagem que diz o limite do plano e como liberar mais.
"""
import json
from contextlib import closing
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import db
from .config import settings

PLAN_NAMES = {"community": "Free", "team": "Pro", "enterprise": "Enterprise"}
# Cotas do Free quando o gateway não repassou nenhuma (espelham `TIER_QUOTAS["community"]` do auth-tenant-service)
FREE_QUOTAS = {"max_datasets": 5, "max_upload_mb": 10}
PRO_DATASETS = 100  # só para a mensagem de upgrade do Free


@dataclass(frozen=True)
class Plan:
    tier: str
    name: str
    tenant_id: str
    max_datasets: int | None  # None = sem limite
    max_upload_mb: int | None


def current_plan(request: Request) -> Plan:
    tenant_id = request.headers.get("x-tenant-id") or settings.default_tenant_id
    if not settings.auth_enabled:
        return Plan("enterprise", "Sem autenticação", tenant_id, None, None)
    tier = request.headers.get("x-tenant-tier") or "community"
    quotas = dict(FREE_QUOTAS)
    raw = request.headers.get("x-tenant-quotas")
    if raw and request.headers.get("x-tenant-tier"):
        try:
            parsed = json.loads(raw)
            quotas.update({k: parsed[k] for k in FREE_QUOTAS if isinstance(parsed.get(k), int)})
        except ValueError:
            pass  # cabeçalho ilegível: fica nos limites do Free
    return Plan(tier, PLAN_NAMES.get(tier, tier), tenant_id, quotas["max_datasets"], quotas["max_upload_mb"])


def _upgrade_hint(plan: Plan) -> str:
    if plan.tier == "community":
        return f"Faça upgrade para o plano Pro (menu Planos > Assinar o Pro) para liberar até {PRO_DATASETS} datasets e arquivos maiores."
    if plan.tier == "team":
        return "Apague datasets que não usa ou fale com a nossa equipe sobre o plano Enterprise."
    return "Apague datasets que não usa para liberar espaço."


def count_datasets(tenant_id: str) -> int:
    with closing(db.connect()) as con:
        return con.execute("SELECT COUNT(*) FROM datasets WHERE tenant_id = ?", [tenant_id]).fetchone()[0]


def check_can_create_dataset(request: Request) -> Plan:
    """Dependência: barra a criação de mais um dataset quando a organização já está no limite do plano."""
    plan = current_plan(request)
    if plan.max_datasets is not None and count_datasets(plan.tenant_id) >= plan.max_datasets:
        raise HTTPException(
            402,
            f"Limite do plano {plan.name}: até {plan.max_datasets} datasets por organização (você já tem {plan.max_datasets}). "
            + _upgrade_hint(plan),
        )
    return plan


def max_upload_bytes(plan: Plan) -> int:
    """O menor entre o teto do servidor e o do plano."""
    server = settings.max_upload_mb
    return (min(server, plan.max_upload_mb) if plan.max_upload_mb is not None else server) * 1024 * 1024


def upload_too_big(plan: Plan) -> HTTPException:
    server_cap = plan.max_upload_mb is None or settings.max_upload_mb <= plan.max_upload_mb
    if server_cap:
        return HTTPException(413, f"file exceeds {settings.max_upload_mb} MB")
    return HTTPException(
        402, f"Limite do plano {plan.name}: arquivos de até {plan.max_upload_mb} MB por dataset. " + _upgrade_hint(plan)
    )
