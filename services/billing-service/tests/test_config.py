import logging

import pytest
from pydantic import ValidationError

from billing_service.config import DEV_STRIPE_SECRET_KEY, DEV_STRIPE_WEBHOOK_SECRET, PLACEHOLDER_PRICES, Settings, stripe_price_ids

REAL = dict(stripe_secret_key="sk_live_abcdefghijklmnop", stripe_webhook_secret="whsec_real_secret_value",
            stripe_mock_mode=False)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ENVIRONMENT", "STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_MOCK_MODE", "APP_URL", "STRIPE_PRICE_ID",
                "STRIPE_PRICE_TEAM_MONTHLY", "STRIPE_PRICE_TEAM_YEARLY", "STRIPE_PRICE_ENTERPRISE_MONTHLY", "STRIPE_PRICE_ENTERPRISE_YEARLY",
                "BILLING_SUCCESS_URL_DEFAULT", "BILLING_CANCEL_URL_DEFAULT", "BILLING_RETURN_URL_DEFAULT"):
        monkeypatch.delenv(var, raising=False)


def test_development_defaults_work_and_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="billing_service.config"):
        s = Settings()
    assert s.stripe_mock_mode is True and s.stripe_secret_key == DEV_STRIPE_SECRET_KEY
    assert "STRIPE_MOCK_MODE ativo" in caplog.text


def test_empty_stripe_vars_behave_as_unset(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    s = Settings()
    assert s.stripe_secret_key == DEV_STRIPE_SECRET_KEY
    assert s.stripe_webhook_secret == DEV_STRIPE_WEBHOOK_SECRET


def test_production_rejects_mock_mode():
    with pytest.raises(ValidationError, match="STRIPE_MOCK_MODE=true"):
        Settings(environment="production", **{**REAL, "stripe_mock_mode": True})


def test_production_rejects_dev_credentials():
    with pytest.raises(ValidationError) as exc:
        Settings(environment="production", stripe_mock_mode=False)
    msg = str(exc.value)
    assert "STRIPE_SECRET_KEY" in msg and "STRIPE_WEBHOOK_SECRET" in msg


def test_production_rejects_empty_credentials_from_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("STRIPE_MOCK_MODE", "false")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    with pytest.raises(ValidationError, match="STRIPE_SECRET_KEY"):
        Settings()


def test_production_accepts_real_configuration():
    assert Settings(environment="production", **REAL).is_production


def test_validation_error_does_not_leak_secrets():
    with pytest.raises(ValidationError) as exc:
        Settings(environment="production", stripe_secret_key="sk_live_SUPERSECRET123",
                 stripe_webhook_secret="whsec_SUPERSECRET456", stripe_mock_mode=True)
    assert "SUPERSECRET" not in str(exc.value)


# ---------- APP_URL e IDs de preço (nomes usados em outros projetos: APP_URL, STRIPE_PRICE_ID) ----------

def test_defaults_keep_dev_urls_and_placeholder_prices():
    s = Settings()
    assert s.billing_success_url_default.startswith("http://localhost:3000/")
    assert stripe_price_ids(s) == PLACEHOLDER_PRICES


def test_app_url_drives_the_redirect_urls(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.exemplo.com/")   # barra final não duplica
    s = Settings()
    assert s.billing_success_url_default == "https://app.exemplo.com/?billing=success&session_id={CHECKOUT_SESSION_ID}"
    assert s.billing_cancel_url_default == "https://app.exemplo.com/?billing=canceled"
    assert s.billing_return_url_default == "https://app.exemplo.com/"


def test_app_url_without_scheme_assumes_https(monkeypatch):
    monkeypatch.setenv("APP_URL", "app.exemplo.com")
    assert Settings().billing_return_url_default == "https://app.exemplo.com/"


def test_explicit_redirect_url_wins_over_app_url(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.exemplo.com")
    monkeypatch.setenv("BILLING_CANCEL_URL_DEFAULT", "https://outro.site/cancelou")
    s = Settings()
    assert s.billing_cancel_url_default == "https://outro.site/cancelou"
    assert s.billing_success_url_default.startswith("https://app.exemplo.com/")   # os demais seguem o APP_URL


def test_stripe_price_id_is_the_team_monthly_price_only(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_1ABC")
    ids = stripe_price_ids(Settings())
    assert ids["team_monthly"] == "price_1ABC"
    # um preço só não vira os outros três: o anual/Enterprise ficam como estavam (nunca cobrar o preço errado)
    assert ids["team_yearly"] == PLACEHOLDER_PRICES["team_yearly"]
    assert ids["enterprise_monthly"] == PLACEHOLDER_PRICES["enterprise_monthly"]


def test_specific_price_vars_override_and_cover_every_plan(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_generic")
    for var, value in (("TEAM_MONTHLY", "price_tm"), ("TEAM_YEARLY", "price_ty"), ("ENTERPRISE_MONTHLY", "price_em"), ("ENTERPRISE_YEARLY", "price_ey")):
        monkeypatch.setenv(f"STRIPE_PRICE_{var}", value)
    assert stripe_price_ids(Settings()) == {"team_monthly": "price_tm", "team_yearly": "price_ty", "enterprise_monthly": "price_em", "enterprise_yearly": "price_ey"}


def test_blank_price_vars_behave_as_unset(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_ID", "  ")
    monkeypatch.setenv("STRIPE_PRICE_TEAM_MONTHLY", "")
    assert stripe_price_ids(Settings()) == PLACEHOLDER_PRICES


def test_real_stripe_with_placeholder_prices_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="billing_service.config"):
        Settings(environment="production", **REAL)
    assert "IDs de exemplo" in caplog.text and "team_monthly" in caplog.text


def test_real_stripe_with_all_prices_does_not_warn(caplog):
    prices = dict(stripe_price_team_monthly="p1", stripe_price_team_yearly="p2", stripe_price_enterprise_monthly="p3", stripe_price_enterprise_yearly="p4")
    with caplog.at_level(logging.WARNING, logger="billing_service.config"):
        Settings(environment="production", **REAL, **prices)
    assert "IDs de exemplo" not in caplog.text


def test_plans_use_the_configured_prices_at_import():
    import os, subprocess, sys
    code = "from billing_service.config import PLANS; print(PLANS['team']['stripe_price_id_monthly'], PLANS['enterprise']['stripe_price_id_yearly'])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env={**os.environ, "STRIPE_PRICE_ID": "price_1ABC", "STRIPE_PRICE_ENTERPRISE_YEARLY": "price_ey"}).stdout.split()
    assert out == ["price_1ABC", "price_ey"]
