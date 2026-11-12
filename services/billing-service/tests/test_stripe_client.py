"""Com STRIPE_MOCK_MODE=false o cliente nunca simula: falta de configuração ou recusa do Stripe vira erro explícito."""
import pytest
from httpx import ASGITransport, AsyncClient

from billing_service.db import BillingStore
from billing_service.main import app, get_billing_store
from billing_service.stripe_client import StripeClient, StripeUnavailable


def real_client(monkeypatch, secret="sk_test_realkey", webhook="whsec_real"):
    c = StripeClient()
    monkeypatch.setattr(c, "mock_mode", False)
    monkeypatch.setattr(c, "secret_key", secret)
    monkeypatch.setattr(c, "webhook_secret", webhook)
    return c


def test_mock_mode_continua_simulando(monkeypatch):
    c = StripeClient()
    monkeypatch.setattr(c, "mock_mode", True)
    assert c.get_or_create_customer("t1") == "cus_mock_t1"
    assert c.create_checkout_session("t1", "cus_mock_t1", "team", "monthly", "http://s", "http://c")["url"].startswith("https://checkout.stripe.com/")
    assert "billing.stripe.com" in c.create_portal_session("cus_mock_t1", "http://r")["url"]


@pytest.mark.parametrize("secret", ["", "sk_test_placeholder_x", "sk_test_metastatistic"])
def test_modo_real_sem_chave_valida_falha_com_503(monkeypatch, secret):
    c = real_client(monkeypatch, secret=secret)
    for call in (
        lambda: c.get_or_create_customer("t1"),
        lambda: c.create_checkout_session("t1", "cus_1", "team", "monthly", "http://s", "http://c"),
        lambda: c.create_portal_session("cus_1", "http://r"),
    ):
        with pytest.raises(StripeUnavailable) as e:
            call()
        assert e.value.status_code == 503
        assert "STRIPE_SECRET_KEY" in str(e.value)


def test_modo_real_com_preco_de_exemplo_falha_com_503(monkeypatch):
    c = real_client(monkeypatch)
    with pytest.raises(StripeUnavailable) as e:
        c.create_checkout_session("t1", "cus_1", "team", "yearly", "http://s", "http://c")
    assert e.value.status_code == 503
    assert "STRIPE_PRICE_TEAM_YEARLY" in str(e.value)


def test_modo_real_erro_do_stripe_vira_502(monkeypatch):
    import stripe

    def boom(**_):
        raise RuntimeError("No such price")

    monkeypatch.setattr(stripe.Customer, "create", boom)
    monkeypatch.setattr(stripe.checkout.Session, "create", boom)
    monkeypatch.setattr(stripe.billing_portal.Session, "create", boom)
    c = real_client(monkeypatch)
    monkeypatch.setitem(__import__("billing_service.config", fromlist=["PLANS"]).PLANS["team"], "stripe_price_id_monthly", "price_real")
    for call in (
        lambda: c.get_or_create_customer("t1"),
        lambda: c.create_checkout_session("t1", "cus_1", "team", "monthly", "http://s", "http://c"),
        lambda: c.create_portal_session("cus_1", "http://r"),
    ):
        with pytest.raises(StripeUnavailable) as e:
            call()
        assert e.value.status_code == 502
        assert "No such price" in str(e.value)


def test_webhook_sem_segredo_no_modo_real_e_recusado(monkeypatch):
    c = real_client(monkeypatch, webhook="")
    with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
        c.verify_webhook_event(b"{}", "t=1,v1=abc")


@pytest.mark.asyncio
async def test_endpoint_checkout_devolve_503_e_nao_grava_sessao_falsa(monkeypatch, tmp_path):
    from billing_service import main as m

    store = BillingStore(str(tmp_path / "b.db"))
    app.dependency_overrides[get_billing_store] = lambda: store
    monkeypatch.setattr(m.stripe_client, "mock_mode", False)
    monkeypatch.setattr(m.stripe_client, "secret_key", "")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/billing/checkout", json={"plan_id": "team", "billing_cycle": "monthly"}, headers={"X-Tenant-ID": "t9"})
        assert r.status_code == 503
        assert "STRIPE_SECRET_KEY" in r.json()["detail"]
        assert store.get_customer("t9") is None
    finally:
        app.dependency_overrides.clear()
