import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from billing_service.config import PLANS, settings
from billing_service.db import BillingStore
from billing_service.models import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalRequest,
    CustomerPortalResponse,
    InvoiceResponse,
    PlanInfo,
    SubscriptionResponse,
    WebhookEventResponse,
)
from billing_service.stripe_client import StripeUnavailable, stripe_client

logger = logging.getLogger(__name__)

billing_store_instance: Optional[BillingStore] = None


def get_billing_store() -> BillingStore:
    global billing_store_instance
    if billing_store_instance is None:
        billing_store_instance = BillingStore(settings.database_url)
    return billing_store_instance


app = FastAPI(
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
    """Retorna os planos comerciais disponíveis (Community, Team e Enterprise)."""
    return [PlanInfo(**plan_data) for plan_data in PLANS.values()]


# ==========================================
# Subscriptions
# ==========================================


@app.get("/billing/subscription", response_model=SubscriptionResponse)
def get_subscription(
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    store: BillingStore = Depends(get_billing_store),
):
    """Retorna a assinatura ativa do tenant ou o plano Community gratuito padrão."""
    sub = store.get_subscription_by_tenant(x_tenant_id)
    if sub:
        return sub

    # Se não houver assinatura registrada, retorna o estado padrão (Community)
    now_iso = datetime.now(timezone.utc).isoformat()
    return SubscriptionResponse(
        id=f"sub_community_{x_tenant_id}",
        tenant_id=x_tenant_id,
        customer_id=f"cus_{x_tenant_id}",
        stripe_subscription_id=None,
        plan_id="community",
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

    if payload.plan_id == "community":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Community plan is free and does not require checkout. Downgrade via subscription cancel.",
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


@app.post("/billing/webhook", response_model=WebhookEventResponse)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    store: BillingStore = Depends(get_billing_store),
):
    """
    Processa webhooks oficiais do Stripe:
    - checkout.session.completed: ativa assinatura e atualiza tier no auth-tenant-service
    - customer.subscription.updated: sincroniza status/tier
    - customer.subscription.deleted: cancela assinatura e rebaixa tenant para community
    - invoice.payment_succeeded: registra fatura paga
    - invoice.payment_failed: registra falha de pagamento e marca past_due
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
    event_data = event.get("data", {}).get("object", {})

    processed = False
    detail = None

    if event_type == "checkout.session.completed":
        customer_id = event_data.get("customer")
        metadata = event_data.get("metadata", {})
        tenant_id = (
            event_data.get("client_reference_id")
            or metadata.get("tenant_id")
            or (store.get_tenant_by_customer_id(customer_id) if customer_id else None)
            or "default"
        )
        plan_id = metadata.get("plan_id", "team")
        tier = metadata.get("tier") or PLANS.get(plan_id, {}).get("tier", "team")
        stripe_sub_id = event_data.get("subscription")

        if customer_id:
            store.save_customer(tenant_id, customer_id)

        store.upsert_subscription(
            tenant_id=tenant_id,
            customer_id=customer_id or f"cus_{tenant_id}",
            plan_id=plan_id,
            tier=tier,
            status="active",
            stripe_subscription_id=stripe_sub_id,
        )

        # Notifica auth-tenant-service para aplicar o novo tier
        await notify_tenant_tier_change(tenant_id, tier)
        processed = True
        detail = f"Subscription activated for tenant {tenant_id} on tier {tier}"

    elif event_type == "customer.subscription.updated":
        stripe_sub_id = event_data.get("id")
        customer_id = event_data.get("customer")
        status_sub = event_data.get("status", "active")
        cancel_at_period_end = bool(event_data.get("cancel_at_period_end", False))
        period_start = event_data.get("current_period_start")
        period_end = event_data.get("current_period_end")

        start_iso = datetime.fromtimestamp(period_start, timezone.utc).isoformat() if period_start else None
        end_iso = datetime.fromtimestamp(period_end, timezone.utc).isoformat() if period_end else None

        existing_sub = store.get_subscription_by_stripe_id(stripe_sub_id) if stripe_sub_id else None
        tenant_id = (
            existing_sub.tenant_id
            if existing_sub
            else (store.get_tenant_by_customer_id(customer_id) if customer_id else "default")
        )

        plan_id = existing_sub.plan_id if existing_sub else "team"
        tier = existing_sub.tier if existing_sub else "team"

        # Verifica se os itens contêm novo plan_id
        items = event_data.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id")
            for pid, pdata in PLANS.items():
                if price_id in (pdata.get("stripe_price_id_monthly"), pdata.get("stripe_price_id_yearly")):
                    plan_id = pid
                    tier = pdata["tier"]
                    break

        store.upsert_subscription(
            tenant_id=tenant_id,
            customer_id=customer_id or (existing_sub.customer_id if existing_sub else f"cus_{tenant_id}"),
            plan_id=plan_id,
            tier=tier,
            status=status_sub,
            stripe_subscription_id=stripe_sub_id,
            current_period_start=start_iso,
            current_period_end=end_iso,
            cancel_at_period_end=cancel_at_period_end,
        )

        if status_sub == "active":
            await notify_tenant_tier_change(tenant_id, tier)

        processed = True
        detail = f"Subscription {stripe_sub_id} updated: status={status_sub}, tier={tier}"

    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = event_data.get("id")
        customer_id = event_data.get("customer")
        existing_sub = store.get_subscription_by_stripe_id(stripe_sub_id) if stripe_sub_id else None
        tenant_id = (
            existing_sub.tenant_id
            if existing_sub
            else (store.get_tenant_by_customer_id(customer_id) if customer_id else "default")
        )

        if existing_sub:
            store.upsert_subscription(
                tenant_id=tenant_id,
                customer_id=existing_sub.customer_id,
                plan_id=existing_sub.plan_id,
                tier=existing_sub.tier,
                status="canceled",
                stripe_subscription_id=stripe_sub_id,
            )

        # Rebaixa tenant para tier community
        await notify_tenant_tier_change(tenant_id, "community")
        processed = True
        detail = f"Subscription {stripe_sub_id} deleted. Tenant {tenant_id} downgraded to community"

    elif event_type == "invoice.payment_succeeded":
        stripe_inv_id = event_data.get("id")
        customer_id = event_data.get("customer")
        sub_id = event_data.get("subscription")
        amount_due = event_data.get("amount_due", 0)
        amount_paid = event_data.get("amount_paid", 0)
        currency = event_data.get("currency", "usd")
        hosted_url = event_data.get("hosted_invoice_url")

        existing_sub = store.get_subscription_by_stripe_id(sub_id) if sub_id else None
        tenant_id = (
            existing_sub.tenant_id
            if existing_sub
            else (store.get_tenant_by_customer_id(customer_id) if customer_id else "default")
        )

        store.save_invoice(
            tenant_id=tenant_id,
            amount_due=amount_due,
            amount_paid=amount_paid,
            status="paid",
            subscription_id=sub_id,
            stripe_invoice_id=stripe_inv_id,
            currency=currency,
            hosted_invoice_url=hosted_url,
        )
        processed = True
        detail = f"Invoice {stripe_inv_id} recorded as paid for tenant {tenant_id}"

    elif event_type == "invoice.payment_failed":
        stripe_inv_id = event_data.get("id")
        customer_id = event_data.get("customer")
        sub_id = event_data.get("subscription")
        amount_due = event_data.get("amount_due", 0)
        amount_paid = event_data.get("amount_paid", 0)
        currency = event_data.get("currency", "usd")
        hosted_url = event_data.get("hosted_invoice_url")

        existing_sub = store.get_subscription_by_stripe_id(sub_id) if sub_id else None
        tenant_id = (
            existing_sub.tenant_id
            if existing_sub
            else (store.get_tenant_by_customer_id(customer_id) if customer_id else "default")
        )

        store.save_invoice(
            tenant_id=tenant_id,
            amount_due=amount_due,
            amount_paid=amount_paid,
            status="open",
            subscription_id=sub_id,
            stripe_invoice_id=stripe_inv_id,
            currency=currency,
            hosted_invoice_url=hosted_url,
        )

        # Marca assinatura como past_due se existir
        if existing_sub:
            store.upsert_subscription(
                tenant_id=tenant_id,
                customer_id=existing_sub.customer_id,
                plan_id=existing_sub.plan_id,
                tier=existing_sub.tier,
                status="past_due",
                stripe_subscription_id=sub_id,
            )

        processed = True
        detail = f"Invoice {stripe_inv_id} recorded as failed/past_due for tenant {tenant_id}"

    else:
        detail = f"Unhandled event type: {event_type}"

    return WebhookEventResponse(
        received=True,
        event_type=event_type,
        processed=processed,
        detail=detail,
    )
