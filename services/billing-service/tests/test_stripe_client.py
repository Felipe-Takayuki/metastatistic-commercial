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
    assert c.create_checkout_session("t1", "cus_mock_t1", "pro", "monthly", "http://s", "http://c")["url"].startswith("https://checkout.stripe.com/")
    assert "billing.stripe.com" in c.create_portal_session("cus_mock_t1", "http://r")["url"]


@pytest.mark.parametrize("secret", ["", "sk_test_placeholder_x", "sk_test_metastatistic"])
def test_modo_real_sem_chave_valida_falha_com_503(monkeypatch, secret):
    c = real_client(monkeypatch, secret=secret)
    for call in (
        lambda: c.get_or_create_customer("t1"),
        lambda: c.create_checkout_session("t1", "cus_1", "pro", "monthly", "http://s", "http://c"),
        lambda: c.create_portal_session("cus_1", "http://r"),
    ):
        with pytest.raises(StripeUnavailable) as e:
            call()
        assert e.value.status_code == 503
        assert "STRIPE_SECRET_KEY" in str(e.value)


def test_modo_real_com_preco_de_exemplo_falha_com_503(monkeypatch):
    c = real_client(monkeypatch)
    with pytest.raises(StripeUnavailable) as e:
        c.create_checkout_session("t1", "cus_1", "pro", "monthly", "http://s", "http://c")
    assert e.value.status_code == 503
    assert "STRIPE_PRICE_PRO_MONTHLY" in str(e.value)


def test_modo_real_erro_do_stripe_vira_502(monkeypatch):
    import stripe

    def boom(**_):
        raise RuntimeError("No such price")

    monkeypatch.setattr(stripe.Customer, "create", boom)
    monkeypatch.setattr(stripe.checkout.Session, "create", boom)
    monkeypatch.setattr(stripe.billing_portal.Session, "create", boom)
    c = real_client(monkeypatch)
    monkeypatch.setitem(__import__("billing_service.config", fromlist=["PLANS"]).PLANS["pro"], "stripe_price_id_monthly", "price_real")
    for call in (
        lambda: c.get_or_create_customer("t1"),
        lambda: c.create_checkout_session("t1", "cus_1", "pro", "monthly", "http://s", "http://c"),
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
            r = await client.post("/billing/checkout", json={"plan_id": "pro", "billing_cycle": "monthly"}, headers={"X-Tenant-ID": "t9"})
        assert r.status_code == 503
        assert "STRIPE_SECRET_KEY" in r.json()["detail"]
        assert store.get_customer("t9") is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_checkout_descarta_customer_simulado_quando_o_modo_real_esta_ligado(monkeypatch, tmp_path):
    """cus_mock_* gravado no modo mock não existe no Stripe: com o modo real vira um customer de verdade, sem 502."""
    from billing_service import main as m

    store = BillingStore(str(tmp_path / "b.db"))
    store.save_customer("default", "cus_mock_default")
    app.dependency_overrides[get_billing_store] = lambda: store
    monkeypatch.setattr(m.stripe_client, "mock_mode", False)
    monkeypatch.setattr(m.stripe_client, "secret_key", "sk_test_realkey")
    monkeypatch.setattr(m.stripe_client, "get_or_create_customer", lambda tenant, email=None: "cus_real_1")
    usados = []

    def fake_checkout(**kw):
        usados.append(kw["customer_id"])
        return {"session_id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1", "customer_id": kw["customer_id"]}

    monkeypatch.setattr(m.stripe_client, "create_checkout_session", fake_checkout)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/billing/checkout", json={"plan_id": "pro", "billing_cycle": "monthly"}, headers={"X-Tenant-ID": "default"})
        assert r.status_code == 200
        assert usados == ["cus_real_1"]
        assert store.get_customer("default")["customer_id"] == "cus_real_1"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_checkout_mantem_customer_real_e_o_simulado_no_modo_mock(monkeypatch, tmp_path):
    from billing_service import main as m

    store = BillingStore(str(tmp_path / "b.db"))
    store.save_customer("a", "cus_real_a")
    store.save_customer("b", "cus_mock_b")
    app.dependency_overrides[get_billing_store] = lambda: store
    monkeypatch.setattr(m.stripe_client, "mock_mode", False)
    monkeypatch.setattr(m.stripe_client, "get_or_create_customer", lambda tenant, email=None: pytest.fail("não deveria criar"))
    try:
        assert m._customer_id_for("a", store) == "cus_real_a"       # customer real é mantido
        monkeypatch.setattr(m.stripe_client, "mock_mode", True)
        assert m._customer_id_for("b", store) == "cus_mock_b"       # no modo mock o simulado continua valendo
    finally:
        app.dependency_overrides.clear()
