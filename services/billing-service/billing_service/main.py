import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncio
import hashlib
from contextlib import asynccontextmanager
import json

from billing_service.config import PLANS, settings
from billing_service.db import BillingStore
from billing_service.models import (
    AdminEventRow,
    AdminPlanRow,
    AdminSummary,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalRequest,
    CustomerPortalResponse,
    InvoiceResponse,
    PlanInfo,
    SubscriptionResponse,
    WebhookEventResponse,
)
from billing_service.reconcile import reconcile
from billing_service.stripe_client import StripeUnavailable, stripe_client

logger = logging.getLogger(__name__)

# Eventos de negócio (checkout criado, assinatura ativada, pagamento falhou...) em uma linha JSON no log do processo,
# no mesmo formato do apps/api (`metastatistic.events`). Handler próprio: não depende da configuração de logging do uvicorn.
events_log = logging.getLogger("metastatistic.events")
if not events_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    events_log.addHandler(_handler)
    events_log.setLevel(logging.INFO)
    events_log.propagate = False


def business_event(event: str, **fields) -> None:
    events_log.info(json.dumps({"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}, ensure_ascii=False, default=str))

billing_store_instance: Optional[BillingStore] = None


def get_billing_store() -> BillingStore:
    global billing_store_instance
    if billing_store_instance is None:
        billing_store_instance = BillingStore(settings.database_url)
    return billing_store_instance


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Com RECONCILE_INTERVAL_MINUTES > 0, compara o Stripe com o banco de tempos em tempos (cobre webhook perdido)."""
    task = None
    if settings.reconcile_interval_minutes > 0 and not settings.stripe_mock_mode:
        async def loop():
            while True:
                await asyncio.sleep(settings.reconcile_interval_minutes * 60)
                try:
                    remote = stripe_client.list_subscription_states()
                    if remote is not None:
                        fixes = await reconcile(get_billing_store(), remote, notify_tenant_tier_change)
                        business_event("billing.reconciled", checked=len(remote), fixes=len(fixes), scheduled=True)
                except Exception:
                    logger.exception("reconciliação periódica falhou")
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="MetaStatistic Billing Service",
    version="0.1.0",
    description="Stripe Subscriptions & Invoicing Microservice for MetaStatistic Commercial",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StripeUnavailable)
async def _stripe_unavailable_handler(request: Request, exc: StripeUnavailable):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


async def notify_tenant_tier_change(tenant_id: str, new_tier: str) -> bool:
    """Notifica o auth-tenant-service para reajustar o tier e as quotas do tenant."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{settings.auth_service_url.rstrip('/')}/tenants/{tenant_id}/tier",
                json={"tier": new_tier},
            )
            if resp.status_code == 200:
                logger.info(f"Successfully updated tenant {tenant_id} tier to {new_tier}")
                return True
            else:
                logger.warning(f"Failed to update tenant tier on auth service: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.warning(f"Error calling auth-tenant-service for tenant {tenant_id}: {e}")
        return False


# ==========================================
# Health Endpoints
# ==========================================


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    return {"status": "ready"}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "billing-service",
        "version": "0.1.0",
        "stripe_mock_mode": settings.stripe_mock_mode,
    }


# ==========================================
# Plans & Pricing
# ==========================================


@app.get("/billing/plans", response_model=List[PlanInfo])
def list_plans():
    """Retorna os planos vendidos: Free (grátis) e Pro (assinatura mensal em R$)."""
    return [PlanInfo(**plan_data) for plan_data in PLANS.values()]


# ==========================================
# Subscriptions
# ==========================================


@app.get("/billing/subscription", response_model=SubscriptionResponse)
def get_subscription(
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    store: BillingStore = Depends(get_billing_store),
):
    """Retorna a assinatura ativa do tenant ou o plano Free padrão."""
    sub = store.get_subscription_by_tenant(x_tenant_id)
    if sub:
        return sub

    # Se não houver assinatura registrada, retorna o estado padrão (Free)
    now_iso = datetime.now(timezone.utc).isoformat()
    return SubscriptionResponse(
        id=f"sub_free_{x_tenant_id}",
        tenant_id=x_tenant_id,
        customer_id=f"cus_{x_tenant_id}",
        stripe_subscription_id=None,
        plan_id="free",
        tier="community",
        status="active",
        current_period_start=None,
        current_period_end=None,
        cancel_at_period_end=False,
        created_at=now_iso,
        updated_at=now_iso,
    )


# ==========================================
# Checkout & Portal Sessions
# ==========================================


@app.post("/billing/checkout", response_model=CheckoutSessionResponse)
def create_checkout(
    payload: CheckoutSessionRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    store: BillingStore = Depends(get_billing_store),
):
    """Cria uma sessão de Checkout Stripe para upgrade de plano."""
    if payload.plan_id not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan_id '{payload.plan_id}'. Valid options: {list(PLANS.keys())}",
        )

    if payload.plan_id == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Free plan is free and does not require checkout. Downgrade via subscription cancel (portal).",
        )
    if payload.billing_cycle != "monthly":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only the monthly billing cycle is available for the Pro plan.",
        )

    plan = PLANS[payload.plan_id]

    # Recupera ou provisiona customer no Stripe e DB
    customer_info = store.get_customer(x_tenant_id)
    if customer_info:
        customer_id = customer_info["customer_id"]
    else:
        customer_id = stripe_client.get_or_create_customer(x_tenant_id, payload.customer_email)
        store.save_customer(x_tenant_id, customer_id, payload.customer_email)

    success_url = payload.success_url or settings.billing_success_url_default
    cancel_url = payload.cancel_url or settings.billing_cancel_url_default

    session_data = stripe_client.create_checkout_session(
        tenant_id=x_tenant_id,
        customer_id=customer_id,
        plan_id=payload.plan_id,
        billing_cycle=payload.billing_cycle,
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=payload.customer_email,
    )

    business_event("billing.checkout_created", tenant=x_tenant_id, plan=payload.plan_id, session_id=session_data["session_id"])
    return CheckoutSessionResponse(
        session_id=session_data["session_id"],
        url=session_data["url"],
        customer_id=customer_id,
        plan_id=payload.plan_id,
        tier=plan["tier"],
    )


@app.post("/billing/portal", response_model=CustomerPortalResponse)
def create_customer_portal(
    payload: CustomerPortalRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    store: BillingStore = Depends(get_billing_store),
):
    """Cria uma sessão do Stripe Customer Portal para gerenciar método de pagamento e faturas."""
    customer_info = store.get_customer(x_tenant_id)
    if not customer_info:
        customer_id = stripe_client.get_or_create_customer(x_tenant_id)
        store.save_customer(x_tenant_id, customer_id)
    else:
        customer_id = customer_info["customer_id"]

    return_url = payload.return_url or settings.billing_return_url_default
    portal_data = stripe_client.create_portal_session(customer_id, return_url)
    business_event("billing.portal_opened", tenant=x_tenant_id)
    return CustomerPortalResponse(url=portal_data["url"])


# ==========================================
# Invoices
# ==========================================


@app.get("/billing/invoices", response_model=List[InvoiceResponse])
def list_invoices(
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    store: BillingStore = Depends(get_billing_store),
):
    """Lista histórico de faturas do tenant."""
    return store.list_invoices_by_tenant(x_tenant_id)


# ==========================================
# Stripe Webhooks
# ==========================================

WEBHOOK_EVENT_TYPES = (
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
    "invoice.payment_succeeded",  # não é um dos quatro pedidos; alimenta o histórico de faturas
)


def _tenant_for(store: BillingStore, existing_sub, customer_id) -> str:
    if existing_sub:
        return existing_sub.tenant_id
    return (store.get_tenant_by_customer_id(customer_id) if customer_id else None) or "default"


def _plan_from_price(items: list, default_plan: str) -> str:
    if default_plan not in PLANS:  # assinatura gravada antes do catálogo Free/Pro (team/enterprise)
        default_plan = "pro"
    for item in items:
        price_id = item.get("price", {}).get("id")
        for pid, pdata in PLANS.items():
            if price_id and price_id == pdata.get("stripe_price_id_monthly"):
                return pid
    return default_plan


async def _handle_checkout_completed(store: BillingStore, data: dict, created: Optional[int] = None, event_id: Optional[str] = None) -> tuple[str, str]:
    customer_id = data.get("customer")
    metadata = data.get("metadata") or {}
    tenant_id = (
        data.get("client_reference_id")
        or metadata.get("tenant_id")
        or (store.get_tenant_by_customer_id(customer_id) if customer_id else None)
        or "default"
    )
    if store.is_stale(tenant_id, created):
        return tenant_id, "Stale event ignored: a newer subscription event was already applied"
    plan_id = metadata.get("plan_id", "pro")
    if plan_id not in PLANS or plan_id == "free":
        plan_id = "pro"
    tier = PLANS[plan_id]["tier"]
    if customer_id:
        store.save_customer(tenant_id, customer_id)
    store.upsert_subscription(
        tenant_id=tenant_id,
        customer_id=customer_id or f"cus_{tenant_id}",
        plan_id=plan_id,
        tier=tier,
        status="active",
        stripe_subscription_id=data.get("subscription"),
    )
    await notify_tenant_tier_change(tenant_id, tier)
    store.advance_clock(tenant_id, created, event_id)
    return tenant_id, f"Subscription activated for tenant {tenant_id} on plan {plan_id}"


async def _handle_subscription_updated(store: BillingStore, data: dict, created: Optional[int] = None, event_id: Optional[str] = None) -> tuple[str, str]:
    stripe_sub_id = data.get("id")
    customer_id = data.get("customer")
    status_sub = data.get("status", "active")
    period_start, period_end = data.get("current_period_start"), data.get("current_period_end")
    start_iso = datetime.fromtimestamp(period_start, timezone.utc).isoformat() if period_start else None
    end_iso = datetime.fromtimestamp(period_end, timezone.utc).isoformat() if period_end else None

    existing_sub = store.get_subscription_by_stripe_id(stripe_sub_id) if stripe_sub_id else None
    tenant_id = _tenant_for(store, existing_sub, customer_id)
    if store.is_stale(tenant_id, created):
        return tenant_id, "Stale event ignored: a newer subscription event was already applied"
    plan_id = _plan_from_price(data.get("items", {}).get("data", []), existing_sub.plan_id if existing_sub else "pro")
    tier = PLANS[plan_id]["tier"]

    store.upsert_subscription(
        tenant_id=tenant_id,
        customer_id=customer_id or (existing_sub.customer_id if existing_sub else f"cus_{tenant_id}"),
        plan_id=plan_id,
        tier=tier,
        status=status_sub,
        stripe_subscription_id=stripe_sub_id,
        current_period_start=start_iso,
        current_period_end=end_iso,
        cancel_at_period_end=bool(data.get("cancel_at_period_end", False)),
    )
    if status_sub == "active":
        await notify_tenant_tier_change(tenant_id, tier)
    store.advance_clock(tenant_id, created, event_id)
    return tenant_id, f"Subscription {stripe_sub_id} updated: status={status_sub}, plan={plan_id}"


async def _handle_subscription_deleted(store: BillingStore, data: dict, created: Optional[int] = None, event_id: Optional[str] = None) -> tuple[str, str]:
    stripe_sub_id = data.get("id")
    existing_sub = store.get_subscription_by_stripe_id(stripe_sub_id) if stripe_sub_id else None
    tenant_id = _tenant_for(store, existing_sub, data.get("customer"))
    if store.is_stale(tenant_id, created):
        return tenant_id, "Stale event ignored: a newer subscription event was already applied"
    if existing_sub:
        store.upsert_subscription(
            tenant_id=tenant_id,
            customer_id=existing_sub.customer_id,
            plan_id=existing_sub.plan_id,
            tier=existing_sub.tier,
            status="canceled",
            stripe_subscription_id=stripe_sub_id,
        )
    await notify_tenant_tier_change(tenant_id, "community")
    store.advance_clock(tenant_id, created, event_id)
    return tenant_id, f"Subscription {stripe_sub_id} deleted. Tenant {tenant_id} downgraded to Free"


def _record_invoice(store: BillingStore, data: dict, invoice_status: str):
    sub_id = data.get("subscription")
    existing_sub = store.get_subscription_by_stripe_id(sub_id) if sub_id else None
    tenant_id = _tenant_for(store, existing_sub, data.get("customer"))
    store.save_invoice(
        tenant_id=tenant_id,
        amount_due=data.get("amount_due", 0),
        amount_paid=data.get("amount_paid", 0),
        status=invoice_status,
        subscription_id=sub_id,
        stripe_invoice_id=data.get("id"),
        currency=data.get("currency", "brl"),
        hosted_invoice_url=data.get("hosted_invoice_url"),
    )
    return tenant_id, existing_sub, sub_id


async def _handle_invoice_succeeded(store: BillingStore, data: dict, created: Optional[int] = None, event_id: Optional[str] = None) -> tuple[str, str]:
    tenant_id, _, _ = _record_invoice(store, data, "paid")
    return tenant_id, f"Invoice {data.get('id')} recorded as paid for tenant {tenant_id}"


async def _handle_invoice_failed(store: BillingStore, data: dict, created: Optional[int] = None, event_id: Optional[str] = None) -> tuple[str, str]:
    tenant_id, existing_sub, sub_id = _record_invoice(store, data, "open")
    if store.is_stale(tenant_id, created):  # a fatura fica registrada, mas o status não volta atrás
        return tenant_id, "Stale event ignored: invoice recorded, subscription status kept (a newer event was already applied)"
    if existing_sub:  # o plano continua (o Stripe ainda retenta a cobrança); se esgotar, vem subscription.deleted
        store.upsert_subscription(
            tenant_id=tenant_id,
            customer_id=existing_sub.customer_id,
            plan_id=existing_sub.plan_id,
            tier=existing_sub.tier,
            status="past_due",
            stripe_subscription_id=sub_id,
        )
    store.advance_clock(tenant_id, created, event_id)
    return tenant_id, f"Invoice {data.get('id')} recorded as failed/past_due for tenant {tenant_id}"


_WEBHOOK_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.payment_failed": _handle_invoice_failed,
    "invoice.payment_succeeded": _handle_invoice_succeeded,
}


@app.post("/billing/webhook", response_model=WebhookEventResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    store: BillingStore = Depends(get_billing_store),
):
    """
    Webhook do Stripe, validado pela assinatura (`Stripe-Signature`) e idempotente pelo `event.id`:
    - checkout.session.completed: ativa o plano Pro e atualiza o tier no auth-tenant-service
    - customer.subscription.updated: sincroniza status, período e plano
    - customer.subscription.deleted: cancela e rebaixa o tenant para Free
    - invoice.payment_failed: registra a fatura em aberto e marca a assinatura como past_due
    (+ invoice.payment_succeeded: registra a fatura paga)
    O Stripe reentrega eventos (timeout, retentativa): a segunda entrega responde 200 sem repetir o efeito.
    """
    body = await request.body()
    try:
        event = stripe_client.verify_webhook_event(body, stripe_signature)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook verification error: {str(e)}",
        )

    event_type = event.get("type", "unknown")
    event_data = (event.get("data") or {}).get("object") or {}
    # eventos reais sempre têm id; sem ele (testes/mock) o hash do corpo faz o papel, então a mesma carga não vale duas vezes
    event_id = str(event.get("id") or "body_" + hashlib.sha256(body).hexdigest()[:32])

    if not store.claim_event(event_id, event_type):
        business_event("billing.webhook_duplicate", event_id=event_id, type=event_type)
        previous = store.get_event(event_id) or {}
        return WebhookEventResponse(
            received=True, event_type=event_type, processed=previous.get("status") == "processed", duplicate=True,
            event_id=event_id, detail=f"Duplicate delivery of {event_id}: already {previous.get('status', 'received')}",
        )

    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler is None:
        detail = f"Unhandled event type: {event_type}"
        store.finish_event(event_id, "ignored", detail)
        return WebhookEventResponse(received=True, event_type=event_type, processed=False, event_id=event_id, detail=detail)

    try:
        tenant_id, detail = await handler(store, event_data, event.get("created"), event_id)
    except Exception as exc:
        # libera o evento: o Stripe vai reenviar (resposta 500) e a nova tentativa precisa poder processar
        logger.exception("webhook %s (%s) falhou", event_id, event_type)
        business_event("billing.webhook_failed", event_id=event_id, type=event_type, error=type(exc).__name__)
        store.finish_event(event_id, "failed", f"{type(exc).__name__}: {exc}"[:300])
        raise HTTPException(status_code=500, detail="Webhook processing failed; the event can be retried") from exc

    if detail.startswith("Stale event ignored"):
        store.finish_event(event_id, "ignored", detail, tenant_id)
        business_event("billing.webhook_stale", tenant=tenant_id, event_id=event_id, type=event_type)
        return WebhookEventResponse(received=True, event_type=event_type, processed=False, event_id=event_id, detail=detail)
    store.finish_event(event_id, "processed", detail, tenant_id)
    business_event(f"billing.{event_type}", tenant=tenant_id, event_id=event_id, detail=detail)
    return WebhookEventResponse(received=True, event_type=event_type, processed=True, event_id=event_id, detail=detail)


# ==========================================
# Painel admin (só o admin da plataforma; o gateway barra os demais)
# ==========================================


async def _fetch_plan_stats() -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.auth_service_url.rstrip('/')}/tenants/stats/plans")
            if resp.status_code == 200:
                return resp.json()
            logger.warning("auth-tenant-service respondeu %s em /tenants/stats/plans", resp.status_code)
    except Exception as exc:
        logger.warning("Não consegui consultar as estatísticas do auth-tenant-service: %s", exc)
    return None


@app.post("/billing/admin/reconcile")
async def admin_reconcile(store: BillingStore = Depends(get_billing_store)):
    """Compara as assinaturas do Stripe com as do banco e corrige as divergências (evento perdido ou fora de ordem)."""
    remote = stripe_client.list_subscription_states()
    if remote is None:
        return {"mode": "mock", "checked": 0, "fixes": [], "detail": "Stripe simulado: não há assinaturas reais para comparar."}
    fixes = await reconcile(store, remote, notify_tenant_tier_change)
    business_event("billing.reconciled", checked=len(remote), fixes=len(fixes))
    return {"mode": "stripe", "checked": len(remote), "fixes": fixes}


@app.get("/billing/admin/summary", response_model=AdminSummary)
async def admin_summary(store: BillingStore = Depends(get_billing_store)):
    """Usuários por plano, assinaturas ativas, MRR de teste e os últimos eventos do Stripe."""
    counts = store.subscription_counts()
    active = {pid: n for (pid, st), n in counts.items() if st in ("active", "trialing") and pid != "free"}
    past_due = sum(n for (pid, st), n in counts.items() if st == "past_due" and pid != "free")
    mrr = sum(PLANS[pid]["price_monthly"] * n for pid, n in active.items() if pid in PLANS)

    stats = await _fetch_plan_stats()
    by_plan = []
    for pid, plan in PLANS.items():
        tenants = users = None
        if stats:
            tier = plan["tier"]
            tenants = stats.get("tenants_by_tier", {}).get(tier, 0)
            users = stats.get("users_by_tier", {}).get(tier, 0)
        by_plan.append(AdminPlanRow(plan_id=pid, name=plan["name"], tenants=tenants, users=users))

    return AdminSummary(
        test_mode=settings.stripe_mock_mode or settings.stripe_secret_key.startswith("sk_test_"),
        mock_mode=settings.stripe_mock_mode,
        failed_events=store.count_events("failed"),
        stuck_events=store.count_events("processing", older_than_s=300),
        active_subscriptions=sum(active.values()),
        past_due_subscriptions=past_due,
        mrr_cents=mrr,
        users_total=stats.get("users_total") if stats else None,
        by_plan=by_plan,
        last_events=[AdminEventRow(**{k: e[k] for k in AdminEventRow.model_fields}) for e in store.list_events(20)],
    )
