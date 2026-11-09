import json
import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from app.config import settings
from app.db import BillingStore
from app.main import app, get_billing_store


@pytest.fixture
def memory_billing_store(tmp_path):
    db_file = tmp_path / "test_billing.db"
    store = BillingStore(str(db_file))
    app.dependency_overrides[get_billing_store] = lambda: store
    yield store
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoints(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "billing-service"

        resp_live = await client.get("/health/live")
        assert resp_live.status_code == 200
        assert resp_live.json()["status"] == "alive"

        resp_ready = await client.get("/health/ready")
        assert resp_ready.status_code == 200
        assert resp_ready.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_list_plans(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/billing/plans")
        assert resp.status_code == 200
        plans = resp.json()
        assert len(plans) == 3
        plan_ids = [p["id"] for p in plans]
        assert "community" in plan_ids
        assert "team" in plan_ids
        assert "enterprise" in plan_ids

        team_plan = next(p for p in plans if p["id"] == "team")
        assert team_plan["price_monthly"] == 4900
        assert team_plan["tier"] == "team"
        assert "postgres_connector" in team_plan["features"]


@pytest.mark.asyncio
async def test_get_default_subscription(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_alpha"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant_alpha"
        assert data["plan_id"] == "community"
        assert data["tier"] == "community"
        assert data["status"] == "active"


@pytest.mark.asyncio
async def test_checkout_session_validation(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Rejeita plano inexistente
        resp_invalid = await client.post(
            "/billing/checkout",
            json={"plan_id": "non_existent_plan"},
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp_invalid.status_code == 400
        assert "Invalid plan_id" in resp_invalid.json()["detail"]

        # Rejeita plano community (gratuito)
        resp_community = await client.post(
            "/billing/checkout",
            json={"plan_id": "community"},
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp_community.status_code == 400
        assert "free" in resp_community.json()["detail"]


@pytest.mark.asyncio
async def test_checkout_session_success(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria checkout para o plano team
        resp = await client.post(
            "/billing/checkout",
            json={
                "plan_id": "team",
                "billing_cycle": "monthly",
                "customer_email": "finance@beta.org",
            },
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"].startswith("cs_test_")
        assert "checkout.stripe.com" in data["url"]
        assert data["plan_id"] == "team"
        assert data["tier"] == "team"
        assert data["customer_id"].startswith("cus_")


@pytest.mark.asyncio
async def test_customer_portal(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/billing/portal",
            json={"return_url": "http://localhost:3000/settings"},
            headers={"X-Tenant-ID": "tenant_gamma"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "billing.stripe.com" in data["url"]
        assert "customer=" in data["url"]


@pytest.mark.asyncio
@respx.mock
async def test_webhook_checkout_completed_and_tier_update(memory_billing_store):
    # Mock da chamada externa ao auth-tenant-service
    auth_route = respx.patch(f"{settings.auth_service_url.rstrip('/')}/tenants/tenant_xyz/tier").mock(
        return_value=Response(200, json={"id": "tenant_xyz", "tier": "enterprise"})
    )

    webhook_payload = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session_1",
                "client_reference_id": "tenant_xyz",
                "customer": "cus_stripe_xyz",
                "subscription": "sub_stripe_real_1",
                "metadata": {
                    "tenant_id": "tenant_xyz",
                    "plan_id": "enterprise",
                    "tier": "enterprise",
                },
            }
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Testa erro com assinatura inválida
        bad_sig = await client.post(
            "/billing/webhook",
            content=json.dumps(webhook_payload),
            headers={"Stripe-Signature": "invalid_signature"},
        )
        assert bad_sig.status_code == 400

        # Testa com assinatura mock válida
        resp = await client.post(
            "/billing/webhook",
            content=json.dumps(webhook_payload),
            headers={"Stripe-Signature": "mock_sig_123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is True
        assert auth_route.called

        # Verifica que a assinatura agora é Enterprise
        sub_resp = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_xyz"})
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["tier"] == "enterprise"
        assert sub_data["plan_id"] == "enterprise"
        assert sub_data["status"] == "active"
        assert sub_data["stripe_subscription_id"] == "sub_stripe_real_1"


@pytest.mark.asyncio
@respx.mock
async def test_webhook_subscription_deleted_downgrade(memory_billing_store):
    auth_route = respx.patch(f"{settings.auth_service_url.rstrip('/')}/tenants/tenant_downgrade/tier").mock(
        return_value=Response(200, json={"id": "tenant_downgrade", "tier": "community"})
    )

    # Pré-popula sub
    memory_billing_store.upsert_subscription(
        tenant_id="tenant_downgrade",
        customer_id="cus_downgrade_1",
        plan_id="team",
        tier="team",
        status="active",
        stripe_subscription_id="sub_stripe_to_delete",
    )

    webhook_payload = {
        "id": "evt_test_delete",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_stripe_to_delete",
                "customer": "cus_downgrade_1",
            }
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/billing/webhook",
            content=json.dumps(webhook_payload),
            headers={"Stripe-Signature": "mock_sig_123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] is True
        assert auth_route.called

        # Assinatura agora está cancelada
        sub_resp = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_downgrade"})
        assert sub_resp.status_code == 200
        assert sub_resp.json()["status"] == "canceled"


@pytest.mark.asyncio
async def test_webhook_invoices_and_multi_tenant_isolation(memory_billing_store):
    # Tenant 1 registra checkout e sub
    memory_billing_store.save_customer("tenant_one", "cus_tenant_1")
    memory_billing_store.upsert_subscription(
        tenant_id="tenant_one",
        customer_id="cus_tenant_1",
        plan_id="team",
        tier="team",
        status="active",
        stripe_subscription_id="sub_t1",
    )

    # Tenant 2 registra checkout e sub
    memory_billing_store.save_customer("tenant_two", "cus_tenant_2")
    memory_billing_store.upsert_subscription(
        tenant_id="tenant_two",
        customer_id="cus_tenant_2",
        plan_id="enterprise",
        tier="enterprise",
        status="active",
        stripe_subscription_id="sub_t2",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invoice pago para Tenant 1
        inv1_payload = {
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_test_1",
                    "customer": "cus_tenant_1",
                    "subscription": "sub_t1",
                    "amount_due": 4900,
                    "amount_paid": 4900,
                    "currency": "usd",
                    "hosted_invoice_url": "https://stripe.com/inv/1",
                }
            },
        }
        resp1 = await client.post(
            "/billing/webhook",
            content=json.dumps(inv1_payload),
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert resp1.status_code == 200

        # Invoice falho para Tenant 2
        inv2_payload = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "in_test_2",
                    "customer": "cus_tenant_2",
                    "subscription": "sub_t2",
                    "amount_due": 29900,
                    "amount_paid": 0,
                    "currency": "usd",
                    "hosted_invoice_url": "https://stripe.com/inv/2",
                }
            },
        }
        resp2 = await client.post(
            "/billing/webhook",
            content=json.dumps(inv2_payload),
            headers={"Stripe-Signature": "valid_sig"},
        )
        assert resp2.status_code == 200

        # Tenant 1 vê apenas sua fatura
        invoices_t1 = await client.get("/billing/invoices", headers={"X-Tenant-ID": "tenant_one"})
        assert invoices_t1.status_code == 200
        t1_list = invoices_t1.json()
        assert len(t1_list) == 1
        assert t1_list[0]["stripe_invoice_id"] == "in_test_1"
        assert t1_list[0]["status"] == "paid"
        assert t1_list[0]["amount_paid"] == 4900

        # Tenant 2 vê apenas sua fatura e sub está past_due
        invoices_t2 = await client.get("/billing/invoices", headers={"X-Tenant-ID": "tenant_two"})
        assert invoices_t2.status_code == 200
        t2_list = invoices_t2.json()
        assert len(t2_list) == 1
        assert t2_list[0]["stripe_invoice_id"] == "in_test_2"
        assert t2_list[0]["status"] == "open"
        assert t2_list[0]["amount_paid"] == 0

        sub_t2 = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_two"})
        assert sub_t2.json()["status"] == "past_due"

        # Tenant 3 não vê faturas
        invoices_t3 = await client.get("/billing/invoices", headers={"X-Tenant-ID": "tenant_three"})
        assert len(invoices_t3.json()) == 0
