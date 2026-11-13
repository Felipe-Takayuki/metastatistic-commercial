import json
import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from billing_service.config import settings
from billing_service.db import BillingStore
from billing_service.main import app, get_billing_store


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
        assert [p["id"] for p in plans] == ["free", "pro"]
        assert all(p["currency"] == "brl" for p in plans)

        free = next(p for p in plans if p["id"] == "free")
        assert free["price_monthly"] == 0 and free["tier"] == "community"
        pro = next(p for p in plans if p["id"] == "pro")
        assert pro["price_monthly"] == 24900  # R$ 249,00 em centavos
        assert pro["tier"] == "team"
        assert pro["quotas"]["max_datasets"] > free["quotas"]["max_datasets"]


@pytest.mark.asyncio
async def test_get_default_subscription(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_alpha"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant_alpha"
        assert data["plan_id"] == "free"
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

        # Rejeita plano free (gratuito)
        resp_community = await client.post(
            "/billing/checkout",
            json={"plan_id": "free"},
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp_community.status_code == 400
        assert "free" in resp_community.json()["detail"].lower()

        # Só cobrança mensal
        resp_yearly = await client.post(
            "/billing/checkout",
            json={"plan_id": "pro", "billing_cycle": "yearly"},
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp_yearly.status_code == 400


@pytest.mark.asyncio
async def test_checkout_session_success(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria checkout para o plano pro
        resp = await client.post(
            "/billing/checkout",
            json={
                "plan_id": "pro",
                "billing_cycle": "monthly",
                "customer_email": "finance@beta.org",
            },
            headers={"X-Tenant-ID": "tenant_beta"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"].startswith("cs_test_")
        assert "checkout.stripe.com" in data["url"]
        assert data["plan_id"] == "pro"
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
        return_value=Response(200, json={"id": "tenant_xyz", "tier": "team"})
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
                    "plan_id": "pro",
                    "tier": "team",
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

        # Verifica que a assinatura agora é Pro
        sub_resp = await client.get("/billing/subscription", headers={"X-Tenant-ID": "tenant_xyz"})
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["tier"] == "team"
        assert sub_data["plan_id"] == "pro"
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
        plan_id="pro",
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
        plan_id="pro",
        tier="team",
        status="active",
        stripe_subscription_id="sub_t1",
    )

    # Tenant 2 registra checkout e sub
    memory_billing_store.save_customer("tenant_two", "cus_tenant_2")
    memory_billing_store.upsert_subscription(
        tenant_id="tenant_two",
        customer_id="cus_tenant_2",
        plan_id="pro",
        tier="team",
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
                    "amount_due": 24900,
                    "amount_paid": 24900,
                    "currency": "brl",
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
                    "amount_due": 24900,
                    "amount_paid": 0,
                    "currency": "brl",
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
        assert t1_list[0]["amount_paid"] == 24900

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


# ======================================================================
# Atividade 11: webhooks idempotentes (4 eventos) e painel admin
# ======================================================================

def _event(event_id, event_type, obj):
    return json.dumps({"id": event_id, "type": event_type, "data": {"object": obj}})


async def _post(client, payload, sig="t=1,v1=mock"):
    return await client.post("/billing/webhook", content=payload, headers={"Stripe-Signature": sig})


@pytest.mark.asyncio
@respx.mock
async def test_webhook_is_idempotent_on_redelivery(memory_billing_store):
    tier_route = respx.patch(f"{settings.auth_service_url.rstrip('/')}/tenants/t_idem/tier").mock(return_value=Response(200, json={}))
    payload = _event("evt_idem_1", "checkout.session.completed", {
        "client_reference_id": "t_idem", "customer": "cus_idem", "subscription": "sub_idem",
        "metadata": {"tenant_id": "t_idem", "plan_id": "pro", "tier": "team"},
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = (await _post(client, payload)).json()
        second_resp = await _post(client, payload)
        second = second_resp.json()
        third = (await _post(client, payload)).json()

    assert first["processed"] is True and first["duplicate"] is False
    assert second_resp.status_code == 200  # o Stripe só para de reentregar com 2xx
    assert second["duplicate"] is True and second["event_id"] == "evt_idem_1"
    assert third["duplicate"] is True
    assert tier_route.call_count == 1  # o efeito colateral (promover o tenant) aconteceu uma vez só
    assert len(memory_billing_store.list_events()) == 1


@pytest.mark.asyncio
@respx.mock
async def test_idempotency_does_not_let_a_stale_redelivery_overwrite_newer_state(memory_billing_store):
    respx.patch(url__regex=r".*/tenants/.*/tier").mock(return_value=Response(200, json={}))
    memory_billing_store.upsert_subscription("t_old", "cus_old", "pro", "team", "active", "sub_old")
    cancel = _event("evt_cancel", "customer.subscription.deleted", {"id": "sub_old", "customer": "cus_old"})
    activate = _event("evt_activate", "customer.subscription.updated", {"id": "sub_old", "customer": "cus_old", "status": "active"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _post(client, activate)
        await _post(client, cancel)
        await _post(client, activate)  # reentrega atrasada do evento antigo: não pode "ressuscitar" a assinatura
        sub = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_old"})).json()
    assert sub["status"] == "canceled"


@pytest.mark.asyncio
@respx.mock
async def test_failed_processing_can_be_retried(memory_billing_store, monkeypatch):
    respx.patch(url__regex=r".*/tenants/.*/tier").mock(return_value=Response(200, json={}))
    from billing_service import main as m

    calls = {"n": 0}
    real = m._handle_subscription_deleted

    async def flaky(store, data, created=None, event_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("banco indisponível")
        return await real(store, data, created, event_id)

    monkeypatch.setitem(m._WEBHOOK_HANDLERS, "customer.subscription.deleted", flaky)
    payload = _event("evt_flaky", "customer.subscription.deleted", {"id": "sub_x", "customer": "cus_x"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await _post(client, payload)
        r2 = await _post(client, payload)  # retentativa do Stripe
    assert r1.status_code == 500
    assert r2.status_code == 200 and r2.json()["processed"] is True and r2.json()["duplicate"] is False
    assert memory_billing_store.get_event("evt_flaky")["status"] == "processed"


@pytest.mark.asyncio
async def test_webhook_rejects_missing_or_invalid_signature(memory_billing_store):
    payload = _event("evt_sig", "invoice.payment_failed", {"id": "in_1", "customer": "c"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post("/billing/webhook", content=payload)
        invalid = await client.post("/billing/webhook", content=payload, headers={"Stripe-Signature": "invalid_signature"})
    assert missing.status_code == 400 and invalid.status_code == 400
    assert memory_billing_store.get_event("evt_sig") is None  # nada é registrado sem assinatura válida


@pytest.mark.asyncio
@respx.mock
async def test_the_four_events_drive_the_subscription_lifecycle(memory_billing_store):
    tier_route = respx.patch(url__regex=r".*/tenants/t_life/tier").mock(return_value=Response(200, json={}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def sub():
            return (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_life"})).json()

        await _post(client, _event("e1", "checkout.session.completed", {
            "client_reference_id": "t_life", "customer": "cus_life", "subscription": "sub_life",
            "metadata": {"tenant_id": "t_life", "plan_id": "pro"}}))
        assert (await sub())["plan_id"] == "pro" and (await sub())["status"] == "active"

        await _post(client, _event("e2", "customer.subscription.updated", {
            "id": "sub_life", "customer": "cus_life", "status": "active", "cancel_at_period_end": True,
            "current_period_start": 1_700_000_000, "current_period_end": 1_702_592_000}))
        s = await sub()
        assert s["cancel_at_period_end"] is True and s["current_period_end"].startswith("2023-12")

        await _post(client, _event("e3", "invoice.payment_failed", {
            "id": "in_life", "customer": "cus_life", "subscription": "sub_life", "amount_due": 24900, "amount_paid": 0, "currency": "brl"}))
        assert (await sub())["status"] == "past_due"

        await _post(client, _event("e4", "customer.subscription.deleted", {"id": "sub_life", "customer": "cus_life"}))
        assert (await sub())["status"] == "canceled"

    tiers = [json.loads(c.request.content)["tier"] for c in tier_route.calls]
    assert tiers == ["team", "team", "community"]  # checkout promove; updated ativo reafirma; deleted rebaixa (payment_failed não mexe no tier)
    statuses = {e["event_type"]: e["status"] for e in memory_billing_store.list_events()}
    assert set(statuses.values()) == {"processed"} and len(statuses) == 4


@pytest.mark.asyncio
async def test_unknown_event_is_acknowledged_and_logged(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await _post(client, _event("evt_other", "charge.refunded", {"id": "ch_1"}))
    assert r.status_code == 200 and r.json()["processed"] is False
    assert memory_billing_store.get_event("evt_other")["status"] == "ignored"


@pytest.mark.asyncio
@respx.mock
async def test_admin_summary(memory_billing_store):
    respx.get(f"{settings.auth_service_url.rstrip('/')}/tenants/stats/plans").mock(return_value=Response(200, json={
        "tenants_by_tier": {"community": 4, "team": 2}, "users_by_tier": {"community": 5, "team": 9}, "users_total": 12}))
    memory_billing_store.upsert_subscription("t_a", "cus_a", "pro", "team", "active", "sub_a")
    memory_billing_store.upsert_subscription("t_b", "cus_b", "pro", "team", "active", "sub_b")
    memory_billing_store.upsert_subscription("t_c", "cus_c", "pro", "team", "past_due", "sub_c")
    memory_billing_store.upsert_subscription("t_d", "cus_d", "pro", "team", "canceled", "sub_d")
    memory_billing_store.claim_event("evt_1", "checkout.session.completed")
    memory_billing_store.finish_event("evt_1", "processed", "ok", "t_a")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = (await client.get("/billing/admin/summary")).json()

    assert data["active_subscriptions"] == 2 and data["past_due_subscriptions"] == 1
    assert data["mrr_cents"] == 2 * 24900 and data["currency"] == "brl" and data["test_mode"] is True and data["mock_mode"] is True
    assert data["users_total"] == 12
    by_plan = {r["plan_id"]: r for r in data["by_plan"]}
    assert by_plan["free"]["users"] == 5 and by_plan["pro"]["users"] == 9 and by_plan["pro"]["tenants"] == 2
    assert data["last_events"][0]["event_id"] == "evt_1" and data["last_events"][0]["tenant_id"] == "t_a"


@pytest.mark.asyncio
@respx.mock
async def test_admin_summary_survives_auth_service_down(memory_billing_store):
    respx.get(f"{settings.auth_service_url.rstrip('/')}/tenants/stats/plans").mock(side_effect=Exception("down"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = (await client.get("/billing/admin/summary")).json()
    assert data["users_total"] is None and all(r["users"] is None for r in data["by_plan"])


@pytest.mark.asyncio
@respx.mock
async def test_business_events_go_to_the_process_log(memory_billing_store):
    import logging
    from billing_service import main as m

    respx.patch(url__regex=r".*/tenants/.*/tier").mock(return_value=Response(200, json={}))
    lines: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    h = Capture()
    m.events_log.addHandler(h)
    try:
        payload = _event("evt_log_1", "checkout.session.completed", {
            "client_reference_id": "t_log", "customer": "cus_log", "subscription": "sub_log", "metadata": {"plan_id": "pro"}})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/billing/checkout", json={"plan_id": "pro"}, headers={"X-Tenant-ID": "t_log"})
            await _post(client, payload)
            await _post(client, payload)
    finally:
        m.events_log.removeHandler(h)
    events = [json.loads(x) for x in lines]
    assert [e["event"] for e in events] == ["billing.checkout_created", "billing.checkout.session.completed", "billing.webhook_duplicate"]
    assert events[1]["tenant"] == "t_log" and events[1]["event_id"] == "evt_log_1"


# ======================================================================
# Issue #8: eventos fora de ordem, reconciliação e alerta de falhas
# ======================================================================

def _ev(event_id, typ, obj, created):
    return json.dumps({"id": event_id, "type": typ, "created": created, "data": {"object": obj}})


@pytest.mark.asyncio
@respx.mock
async def test_older_event_arriving_late_does_not_undo_a_newer_one(memory_billing_store):
    tier = respx.patch(url__regex=r".*/tenants/t_ord/tier").mock(return_value=Response(200, json={}))
    memory_billing_store.upsert_subscription("t_ord", "cus_ord", "pro", "team", "active", "sub_ord")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _post(client, _ev("e_del", "customer.subscription.deleted", {"id": "sub_ord", "customer": "cus_ord"}, 2000))
        late = await _post(client, _ev("e_upd", "customer.subscription.updated", {"id": "sub_ord", "customer": "cus_ord", "status": "active"}, 1000))
        sub = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_ord"})).json()
    assert late.status_code == 200 and late.json()["processed"] is False and "Stale" in late.json()["detail"]
    assert sub["status"] == "canceled"                                   # o cancelamento (mais novo) vale
    assert [json.loads(c.request.content)["tier"] for c in tier.calls] == ["community"]   # nenhuma promoção indevida
    assert memory_billing_store.get_event("e_upd")["status"] == "ignored"


@pytest.mark.asyncio
@respx.mock
async def test_newer_event_after_older_is_applied_and_equal_timestamps_are_fine(memory_billing_store):
    respx.patch(url__regex=r".*/tenants/t_ok/tier").mock(return_value=Response(200, json={}))
    memory_billing_store.upsert_subscription("t_ok", "cus_ok", "pro", "team", "active", "sub_ok")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await _post(client, _ev("o1", "customer.subscription.updated", {"id": "sub_ok", "customer": "cus_ok", "status": "active"}, 1000))
        r2 = await _post(client, _ev("o2", "customer.subscription.updated", {"id": "sub_ok", "customer": "cus_ok", "status": "active", "cancel_at_period_end": True}, 1000))
        r3 = await _post(client, _ev("o3", "customer.subscription.deleted", {"id": "sub_ok", "customer": "cus_ok"}, 3000))
    assert all(r.json()["processed"] for r in (r1, r2, r3))


@pytest.mark.asyncio
async def test_stale_payment_failed_keeps_the_invoice_but_not_the_status(memory_billing_store):
    memory_billing_store.save_customer("t_inv", "cus_inv")
    memory_billing_store.upsert_subscription("t_inv", "cus_inv", "pro", "team", "active", "sub_inv")
    memory_billing_store.advance_clock("t_inv", 5000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _post(client, _ev("f1", "invoice.payment_failed", {"id": "in_x", "customer": "cus_inv", "subscription": "sub_inv", "amount_due": 24900, "amount_paid": 0}, 4000))
        sub = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_inv"})).json()
        invs = (await client.get("/billing/invoices", headers={"X-Tenant-ID": "t_inv"})).json()
    assert sub["status"] == "active" and len(invs) == 1


@pytest.mark.asyncio
@respx.mock
async def test_reconcile_fixes_missed_events(memory_billing_store, monkeypatch):
    from billing_service import main as m

    tier = respx.patch(url__regex=r".*/tenants/.*/tier").mock(return_value=Response(200, json={}))
    memory_billing_store.save_customer("t_paid", "cus_paid")                       # pagou, mas o webhook nunca chegou
    memory_billing_store.upsert_subscription("t_gone", "cus_gone", "pro", "team", "active", "sub_gone")     # cancelada no Stripe, sem evento
    memory_billing_store.upsert_subscription("t_fake", "cus_fake", "pro", "team", "active", "sub_fake")     # promovida sem existir no Stripe
    remote = {
        "sub_paid": {"status": "active", "customer": "cus_paid", "price_id": None, "tenant_id": None, "cancel_at_period_end": False},
        "sub_gone": {"status": "canceled", "customer": "cus_gone", "price_id": None, "tenant_id": None},
    }
    monkeypatch.setattr(m.stripe_client, "list_subscription_states", lambda: remote)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        out = (await client.post("/billing/admin/reconcile")).json()
        paid = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_paid"})).json()
        gone = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_gone"})).json()
        fake = (await client.get("/billing/subscription", headers={"X-Tenant-ID": "t_fake"})).json()
        again = (await client.post("/billing/admin/reconcile")).json()
    assert out["mode"] == "stripe" and out["checked"] == 2 and len(out["fixes"]) == 3
    assert paid["plan_id"] == "pro" and paid["status"] == "active"
    assert gone["status"] == "canceled" and fake["status"] == "canceled"
    assert sorted(json.loads(c.request.content)["tier"] for c in tier.calls) == ["community", "community", "team"]
    assert again["fixes"] == []                                                      # idempotente


@pytest.mark.asyncio
async def test_reconcile_in_mock_mode_is_a_noop(memory_billing_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        out = (await client.post("/billing/admin/reconcile")).json()
    assert out["mode"] == "mock" and out["fixes"] == []


@pytest.mark.asyncio
@respx.mock
async def test_summary_flags_failed_and_stuck_events(memory_billing_store):
    respx.get(f"{settings.auth_service_url.rstrip('/')}/tenants/stats/plans").mock(return_value=Response(200, json={"tenants_by_tier": {}, "users_by_tier": {}, "users_total": 0}))
    memory_billing_store.claim_event("e_fail", "invoice.payment_failed")
    memory_billing_store.finish_event("e_fail", "failed", "boom")
    memory_billing_store.claim_event("e_stuck", "checkout.session.completed")
    with memory_billing_store._get_connection() as c:
        c.execute("UPDATE webhook_events SET received_at = '2020-01-01T00:00:00+00:00' WHERE event_id = 'e_stuck'")
        c.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        data = (await client.get("/billing/admin/summary")).json()
    assert data["failed_events"] == 1 and data["stuck_events"] == 1
