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
    currency: str = "usd"
    features: List[str]
    quotas: Dict[str, Any]
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None


class CheckoutSessionRequest(BaseModel):
    plan_id: str = Field(..., description="Plan ID ('team' or 'enterprise')")
    billing_cycle: BillingCycleType = Field("monthly", description="'monthly' or 'yearly'")
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
    currency: str = "usd"
    status: InvoiceStatusType
    hosted_invoice_url: Optional[str] = None
    created_at: str


class WebhookEventResponse(BaseModel):
    received: bool
    event_type: str
    processed: bool
    detail: Optional[str] = None
