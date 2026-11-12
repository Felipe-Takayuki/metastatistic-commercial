import pytest

from app import authz
from app.config import settings


@pytest.fixture(autouse=True)
def authz_off_by_default(monkeypatch):
    """Os testes de roteamento existentes não carregam sessão; a autorização é testada em test_authz.py."""
    monkeypatch.setattr(settings, "authz_enabled", False)
    authz.clear_cache()
    yield
    authz.clear_cache()
