"""Reconciliação: compara as assinaturas do Stripe (a fonte da verdade do dinheiro) com as do banco e corrige divergências.

Cobre o que o webhook sozinho não garante: evento que nunca chegou (endpoint fora do ar por muito tempo), evento perdido
depois das retentativas do Stripe, ou assinatura criada/cancelada sem passar pelo nosso fluxo. Cada correção usa as
mesmas regras do webhook (Pro ativo promove, cancelada rebaixa para Free, atraso vira past_due).
"""
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from billing_service.config import PLANS
from billing_service.db import BillingStore

logger = logging.getLogger(__name__)
Notify = Callable[[str, str], Awaitable[bool]]

ACTIVE = {"active", "trialing"}
DEAD = {"canceled", "incomplete_expired"}


def _plan_of(price_id: Optional[str]) -> str:
    for pid, p in PLANS.items():
        if price_id and price_id == p.get("stripe_price_id_monthly"):
            return pid
    return "pro"


async def reconcile(store: BillingStore, remote: Dict[str, Dict[str, Any]], notify: Notify) -> List[Dict[str, Any]]:
    """Aplica ao banco o que o Stripe diz e devolve a lista de correções feitas."""
    fixes: List[Dict[str, Any]] = []
    local = {s.stripe_subscription_id: s for s in store.list_subscriptions() if s.stripe_subscription_id}

    for sid, r in remote.items():
        loc = local.get(sid)
        tenant = loc.tenant_id if loc else (store.get_tenant_by_customer_id(r.get("customer") or "") or r.get("tenant_id"))
        if not tenant:
            fixes.append({"subscription": sid, "action": "ignorada: organização desconhecida"})
            continue
        status = r["status"]
        plan_id = _plan_of(r.get("price_id"))
        tier = PLANS[plan_id]["tier"]
        customer = r.get("customer") or (loc.customer_id if loc else f"cus_{tenant}")

        if status in ACTIVE and (loc is None or loc.status != "active" or loc.tier != tier):
            store.upsert_subscription(tenant, customer, plan_id, tier, "active", sid, cancel_at_period_end=r.get("cancel_at_period_end", False))
            await notify(tenant, tier)
            fixes.append({"subscription": sid, "tenant": tenant, "action": f"ativada como {plan_id}", "antes": loc.status if loc else None})
        elif status in DEAD and loc is not None and loc.status != "canceled":
            store.upsert_subscription(tenant, loc.customer_id, loc.plan_id, loc.tier, "canceled", sid)
            await notify(tenant, "community")
            fixes.append({"subscription": sid, "tenant": tenant, "action": "cancelada e rebaixada para Free", "antes": loc.status})
        elif status in {"past_due", "unpaid"} and loc is not None and loc.status not in {"past_due", "canceled"}:
            store.upsert_subscription(tenant, loc.customer_id, loc.plan_id, loc.tier, "past_due", sid)
            fixes.append({"subscription": sid, "tenant": tenant, "action": "marcada como past_due", "antes": loc.status})

    # promovida aqui, mas o Stripe não conhece: não houve pagamento real
    for sid, loc in local.items():
        if sid not in remote and loc.status in {"active", "past_due"}:
            store.upsert_subscription(loc.tenant_id, loc.customer_id, loc.plan_id, loc.tier, "canceled", sid)
            await notify(loc.tenant_id, "community")
            fixes.append({"subscription": sid, "tenant": loc.tenant_id, "action": "cancelada: não existe no Stripe", "antes": loc.status})
    return fixes
