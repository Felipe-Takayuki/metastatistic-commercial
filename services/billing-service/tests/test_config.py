import logging

import pytest
from pydantic import ValidationError

from billing_service.config import DEV_STRIPE_SECRET_KEY, DEV_STRIPE_WEBHOOK_SECRET, Settings

REAL = dict(stripe_secret_key="sk_live_abcdefghijklmnop", stripe_webhook_secret="whsec_real_secret_value",
            stripe_mock_mode=False)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ENVIRONMENT", "STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_MOCK_MODE"):
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
