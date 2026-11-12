import logging

import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET, Settings

STRONG_SECRET = "a-very-strong-and-unique-secret-key-0123456789"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ENVIRONMENT", "JWT_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_development_defaults_work_and_warn(caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s = Settings()
    assert s.environment == "development" and s.jwt_secret_key == DEV_JWT_SECRET
    assert "JWT_SECRET_KEY não definido" in caplog.text


def test_empty_secret_behaves_as_unset(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    assert Settings().jwt_secret_key == DEV_JWT_SECRET


def test_custom_secret_is_used_without_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s = Settings(jwt_secret_key=STRONG_SECRET)
    assert s.jwt_secret_key == STRONG_SECRET
    assert caplog.text == ""


@pytest.mark.parametrize("secret", [
    DEV_JWT_SECRET,                                              # padrão do código
    "change-this-in-production-to-a-secure-256bit-secret",       # placeholder do Helm
    "",                                                          # vazio -> padrão
    "short-secret",                                              # < 32 caracteres
])
def test_production_rejects_insecure_secrets(secret):
    with pytest.raises(ValidationError, match="ENVIRONMENT=production"):
        Settings(environment="production", jwt_secret_key=secret)


def test_production_accepts_strong_secret():
    assert Settings(environment="production", jwt_secret_key=STRONG_SECRET).is_production


def test_production_detected_from_env_var_case_insensitive(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", " Production ")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_SECRET)
    assert Settings().is_production


def test_validation_error_does_not_leak_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(environment="production", jwt_secret_key="SUPERSECRET-too-short")
    assert "SUPERSECRET" not in str(exc.value)


def test_production_rejects_disabled_authz():
    with pytest.raises(ValidationError, match="AUTHZ_ENABLED=false"):
        Settings(environment="production", jwt_secret_key=STRONG_SECRET, authz_enabled=False)


def test_authz_is_enabled_by_default():
    assert Settings().authz_enabled is True
