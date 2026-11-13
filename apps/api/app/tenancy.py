"""Organização (tenant) da requisição em curso.

O gateway confere se o usuário é membro da organização pedida e repassa a verificada em `X-Tenant-ID` (para quem não é
membro, ou sem organização, repassa `default`). Este middleware guarda o valor num ContextVar; datasets, relatórios,
dashboards e coleções filtram por ele, então uma organização nunca lista, abre nem consulta por SQL o que é de outra.

Com a autenticação desligada (demonstração local) não há isolamento: `scope()` devolve None e nada é filtrado.
"""
from contextvars import ContextVar

from .config import settings

_current: ContextVar[str | None] = ContextVar("tenant", default=None)
_correlation: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_org_role: ContextVar[str | None] = ContextVar("org_role", default=None)


def org_role() -> str | None:
    """Papel do usuário NA organização da requisição (owner, admin, statistician, analyst, viewer), verificado pelo gateway."""
    return _org_role.get()


def correlation_id() -> str | None:
    """X-Correlation-ID gerado no gateway: o mesmo id aparece nos logs do gateway, da api e do billing."""
    return _correlation.get()


def scope() -> str | None:
    """Organização a que as consultas se restringem; None = sem isolamento."""
    if not settings.auth_enabled:
        return None
    return _current.get() or settings.default_tenant_id


def and_clause(column: str = "tenant_id") -> tuple[str, list[str]]:
    """Trecho `AND tenant_id = ?` (e o parâmetro) para somar a um WHERE; vazio quando não há isolamento."""
    t = scope()
    return (f" AND {column} = ?", [t]) if t is not None else ("", [])


def current_or_default() -> str:
    return _current.get() or settings.default_tenant_id


class TenantMiddleware:
    """ASGI puro (sem BaseHTTPMiddleware): o ContextVar chega às rotas síncronas, que rodam em thread."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope_, receive, send):
        if scope_["type"] != "http":
            return await self.app(scope_, receive, send)
        tenant = cid = role = None
        for key, value in scope_.get("headers", []):
            if key == b"x-tenant-id":
                tenant = value.decode("latin-1").strip()[:64] or None
            elif key == b"x-tenant-role":
                role = value.decode("latin-1").strip()[:32] or None
            elif key == b"x-correlation-id":
                cid = value.decode("latin-1").strip()[:64] or None
        token, ctoken, rtoken = _current.set(tenant), _correlation.set(cid), _org_role.set(role)
        try:
            await self.app(scope_, receive, send)
        finally:
            _current.reset(token)
            _correlation.reset(ctoken)
            _org_role.reset(rtoken)
