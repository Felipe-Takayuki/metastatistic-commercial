from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

TierType = Literal["community", "team", "enterprise"]
BillingCycleType = Literal["monthly", "yearly"]
SubscriptionStatusType = Literal["active", "canceled", "past_due", "trialing", "incomplete", "unpaid"]
InvoiceStatusType = Literal["paid", "open", "void", "uncollectible"]


class PlanInfo(BaseModel):
    id: str
    name: str
    description: str
    tier: TierType
    price_monthly: int
    price_yearly: int
    currency: str = "brl"
    features: List[str]
    quotas: Dict[str, Any]
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None


class CheckoutSessionRequest(BaseModel):
    plan_id: str = Field(..., description="ID do plano pago ('pro')")
    billing_cycle: BillingCycleType = Field("monthly", description="Só 'monthly' é vendido")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    customer_email: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str
    customer_id: Optional[str] = None
    plan_id: str
    tier: TierType


class CustomerPortalRequest(BaseModel):
    return_url: Optional[str] = None


class CustomerPortalResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    customer_id: str
    stripe_subscription_id: Optional[str] = None
    plan_id: str
    tier: TierType
    status: SubscriptionStatusType
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    created_at: str
    updated_at: str


class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    subscription_id: Optional[str] = None
    stripe_invoice_id: Optional[str] = None
    amount_due: int
    amount_paid: int
    currency: str = "brl"
    status: InvoiceStatusType
    hosted_invoice_url: Optional[str] = None
    created_at: str


class WebhookEventResponse(BaseModel):
    received: bool
    event_type: str
    processed: bool
    duplicate: bool = False
    event_id: Optional[str] = None
    detail: Optional[str] = None


class AdminPlanRow(BaseModel):
    plan_id: str
    name: str
    tenants: Optional[int] = None   # None: não deu para consultar o auth-tenant-service
    users: Optional[int] = None


class AdminEventRow(BaseModel):
    event_id: str
    event_type: str
    tenant_id: Optional[str] = None
    status: str
    detail: Optional[str] = None
    received_at: str
    processed_at: Optional[str] = None


class AdminSummary(BaseModel):
    """Painel do administrador da plataforma. MRR de teste: soma do preço mensal das assinaturas ativas (Stripe em modo de teste)."""
    currency: str = "brl"
    test_mode: bool
    mock_mode: bool = False        # True = Stripe simulado (STRIPE_MOCK_MODE), nenhuma chamada real ao Stripe
    active_subscriptions: int
    past_due_subscriptions: int
    mrr_cents: int
    users_total: Optional[int] = None
    by_plan: List[AdminPlanRow]
    last_events: List[AdminEventRow]
