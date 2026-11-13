"""Autenticação e autorização no gateway.

Antes: o gateway confiava no `X-Tenant-ID` enviado pelo cliente (e num JWT cuja assinatura nunca era verificada), então
qualquer pessoa lia dados de qualquer tenant. Agora:

1. **Quem é você** — a sessão do app (cookie `ms_session`, emitido pelo `apps/api`) é validada com `GET /auth/me`.
2. **Qual tenant você pode usar** — o tenant pedido (header, subdomínio, path ou query) é só um *pedido*; o gateway
   confere no `auth-tenant-service` se o usuário é membro e com qual papel.
3. **O que chega aos serviços** — headers de identidade vindos do cliente são descartados; o gateway injeta os verificados
   (`X-Tenant-ID`, `X-Tenant-Slug`, `X-Tenant-Role`, `X-User-ID`, `X-User-Role`).
4. Endpoints internos (`PATCH /tenants/*/tier`, `POST /audit/events`, `POST /auth/token`...) não são alcançáveis de fora.

Falha fechado: se o `apps/api` ou o `auth-tenant-service` não responderem, a requisição é recusada (503).
"""
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple

import httpx

from app.config import settings
from app.tenant_resolver import resolve_tenant

SESSION_COOKIE = "ms_session"  # emitido pelo apps/api (apps/api/app/security.py)
ADMIN_TENANT_ROLES = {"owner", "admin"}
INTERNAL_TIMEOUT_S = 5.0

# Headers de identidade que só o gateway pode definir.
SPOOFABLE_HEADERS = {"x-tenant-id", "x-tenant-slug", "x-tenant-role", "x-tenant-tier", "x-tenant-quotas", "x-user-id", "x-user-role"}


class Access(Enum):
    PUBLIC = "public"      # sem sessão (login, webhook do Stripe, SSO, frontend estático)
    DENY = "deny"          # só serviço-a-serviço; nunca de fora
    SESSION = "session"    # qualquer usuário autenticado
    MEMBER = "member"      # membro do tenant pedido
    ADMIN = "admin"        # owner/admin do tenant pedido
    PLATFORM_ADMIN = "platform_admin"  # administrador da plataforma (papel `admin` do apps/api), não de um tenant


@dataclass(frozen=True)
class Policy:
    access: Access
    tenant_from: str = "header"            # "header" | "path" | "query"
    path_ref: Optional[str] = None         # tenant extraído do path quando tenant_from == "path"
    body_user_field: Optional[str] = None  # campo do corpo que deve ser o próprio usuário autenticado
    free_tier_only: bool = False           # criação de organização: só nasce no Free; o upgrade é pelo checkout do Stripe
    soft_tenant: bool = False              # SESSION que, se o usuário é membro do tenant pedido, também repassa o plano dele


@dataclass(frozen=True)
class Identity:
    user_id: str
    username: str
    role: str  # papel da plataforma (apps/api): viewer | editor | admin


@dataclass
class Decision:
    allowed: bool
    status: int = 200
    detail: str = ""
    identity: Optional[Identity] = None
    tenant_id: Optional[str] = None
    tenant_slug: Optional[str] = None
    tenant_role: Optional[str] = None
    tenant_tier: Optional[str] = None
    tenant_quotas: Optional[dict] = None
    query_overrides: Dict[str, str] = field(default_factory=dict)


def deny(status: int, detail: str) -> Decision:
    return Decision(allowed=False, status=status, detail=detail)


# ---------------------------------------------------------------------------
# Roteamento: caminho canônico e serviço de destino
# ---------------------------------------------------------------------------

def safe_path(path: str) -> bool:
    """Rejeita caminhos que poderiam ser lidos de forma diferente pelo gateway e pelo serviço de destino."""
    if "\\" in path or "\x00" in path or "%" in path or "//" in path:
        return False
    return not any(seg in (".", "..") for seg in path.split("/"))


def canonical_path(path: str) -> str:
    """`/api/v1/billing/plans`, `/api/billing/plans` e `/billing/plans` -> `/billing/plans` (`/sso/x` -> `/auth/sso/x`)."""
    p = "/" + path.lstrip("/")
    if p.startswith("/api/") and not p.startswith("/api/v1/"):
        p = "/api/v1" + p[4:]
    if p == "/api/v1" or p.startswith("/api/v1/"):
        p = p[len("/api/v1"):] or "/"
    if p == "/sso" or p.startswith("/sso/"):
        p = "/auth" + p
    return p


def service_of(target_url: str) -> str:
    bases = {
        "web": settings.web_url,
        "data_api": settings.data_api_url,
        "auth": settings.auth_service_url,
        "audit": settings.audit_service_url,
        "billing": settings.billing_service_url,
        "stat": settings.stat_orchestrator_url,
        "data_engine": settings.data_engine_service_url,
        "bi_report": settings.bi_report_service_url,
        "export": settings.export_service_url,
    }
    for name, base in bases.items():
        base = base.rstrip("/")
        if target_url == base or target_url.startswith(base + "/"):
            return name
    return "unknown"


FRONTEND_PUBLIC = {"/auth/status", "/auth/login", "/auth/logout", "/auth/setup", "/auth/register"}
SSO_PUBLIC = {"/auth/sso/login", "/auth/sso/saml/acs", "/auth/sso/oidc/callback"}

_TIER_UPDATE = re.compile(r"^/tenants/[^/]+/tier$")
_TENANT_STATS = re.compile(r"^/tenants/stats(/|$)")
_ACCESS_CHECK = re.compile(r"^/tenants/[^/]+/access(/|$)")
_ACCEPT_INVITE = re.compile(r"^/tenants/invitations/[^/]+/accept$")
_TENANT_ONLY = re.compile(r"^/tenants/([^/]+)$")
_TENANT_MEMBERS_READ = re.compile(r"^/tenants/([^/]+)/members$")
_TENANT_SUB = re.compile(r"^/tenants/([^/]+)(/.*)?$")
_SCIM = re.compile(r"^/scim/v2/tenants/([^/]+)(/.*)?$")


def classify(method: str, cp: str, service: str) -> Policy:
    m = method.upper()
    if m == "OPTIONS" or service == "web":
        return Policy(Access.PUBLIC)

    # Somente serviço-a-serviço (billing -> auth atualiza tier; auth -> audit grava eventos; gateway -> auth checa acesso)
    if (
        (m == "PATCH" and _TIER_UPDATE.match(cp))
        or _TENANT_STATS.match(cp)  # estatísticas globais por plano: só o billing-service consulta
        or _ACCESS_CHECK.match(cp)
        or cp == "/auth/token"  # emite token sem autenticar o chamador; ver PLAN.md §7
        or (service == "audit" and m != "GET")
    ):
        return Policy(Access.DENY)

    if cp in FRONTEND_PUBLIC or cp in SSO_PUBLIC or cp == "/auth/verify" or cp.startswith("/health"):
        return Policy(Access.PUBLIC)
    if m == "POST" and cp == "/billing/webhook":  # autenticado pela assinatura do Stripe, no billing-service
        return Policy(Access.PUBLIC)

    if service == "data_api":  # o apps/api aplica seus próprios papéis/propriedade; aqui só exigimos sessão (+ plano do tenant)
        return Policy(Access.SESSION, soft_tenant=True)

    # --- auth-tenant-service ---
    if m == "POST" and cp == "/tenants":
        return Policy(Access.SESSION, body_user_field="owner_id", free_tier_only=True)
    if m == "GET" and cp.startswith("/tenants/by-slug/"):
        return Policy(Access.SESSION)
    if m == "POST" and _ACCEPT_INVITE.match(cp):
        return Policy(Access.SESSION, body_user_field="user_id")
    match = _TENANT_ONLY.match(cp)
    if match and m == "GET":
        return Policy(Access.MEMBER, "path", match.group(1))
    match = _TENANT_MEMBERS_READ.match(cp)
    if match and m == "GET":
        return Policy(Access.MEMBER, "path", match.group(1))
    match = _TENANT_SUB.match(cp)
    if match:  # convites, papéis, remoção de membros, SSO, qualquer outra ação administrativa
        return Policy(Access.ADMIN, "path", match.group(1))
    match = _SCIM.match(cp)
    if match:  # provisionamento: exige admin do tenant (IdPs externos precisam de token por tenant; ver PLAN.md §7)
        return Policy(Access.ADMIN, "path", match.group(1))

    # --- demais serviços ---
    if service == "audit":  # só GET chega aqui
        return Policy(Access.ADMIN, "query")
    if service == "billing" and cp.startswith("/billing/admin"):  # painel com dados de TODAS as organizações
        return Policy(Access.PLATFORM_ADMIN)
    if service == "billing" and m == "POST" and cp in {"/billing/checkout", "/billing/portal"}:
        return Policy(Access.ADMIN)
    return Policy(Access.MEMBER)  # padrão fechado: precisa ser membro do tenant pedido


# ---------------------------------------------------------------------------
# Identidade e associação
# ---------------------------------------------------------------------------

_access_cache: Dict[Tuple[str, str], Tuple[float, dict]] = {}


def clear_cache() -> None:
    _access_cache.clear()


async def fetch_identity(client: httpx.AsyncClient, cookie_header: Optional[str]) -> Tuple[Optional[Identity], Optional[Decision]]:
    if not cookie_header or SESSION_COOKIE not in cookie_header:
        return None, deny(401, "authentication required")
    try:
        resp = await client.get(
            f"{settings.data_api_url.rstrip('/')}/auth/me", headers={"Cookie": cookie_header}, timeout=INTERNAL_TIMEOUT_S
        )
    except httpx.HTTPError:
        return None, deny(503, "authentication service unavailable")
    if resp.status_code in (401, 403):
        return None, deny(401, "authentication required")
    if resp.status_code != 200:
        return None, deny(503, "authentication service unavailable")
    try:
        data = resp.json()
        return Identity(str(data["id"]), str(data.get("username", "")), str(data.get("role", "viewer"))), None
    except Exception:
        return None, deny(503, "authentication service returned an invalid response")


async def fetch_access(client: httpx.AsyncClient, tenant_ref: str, user_id: str) -> Tuple[Optional[dict], Optional[Decision]]:
    """Membro do tenant? Só resultados positivos entram no cache (convite aceito vale na hora; remoção demora até o TTL)."""
    key = (tenant_ref, user_id)
    cached = _access_cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1], None
    try:
        resp = await client.get(
            f"{settings.auth_service_url.rstrip('/')}/tenants/{tenant_ref}/access/{user_id}", timeout=INTERNAL_TIMEOUT_S
        )
    except httpx.HTTPError:
        return None, deny(503, "tenant service unavailable")
    if resp.status_code == 404:
        return None, deny(403, "you are not a member of this tenant")
    if resp.status_code != 200:
        return None, deny(503, "tenant service unavailable")
    access = resp.json()
    if settings.authz_cache_ttl_s > 0:
        _access_cache[key] = (time.monotonic() + settings.authz_cache_ttl_s, access)
    return access, None


# ---------------------------------------------------------------------------
# Decisão
# ---------------------------------------------------------------------------

async def _soft_tenant(client: httpx.AsyncClient, identity: Identity, headers: dict, host: Optional[str]) -> Decision:
    """Nunca recusa: só descobre o plano. Membro do tenant pedido -> repassa o tenant, o plano e as cotas verificados.
    Não membro, tenant inexistente ou workspace padrão -> segue como `default`, sem plano (a API aplica os limites do Free),
    então ninguém ganha limites maiores dizendo ser de um tenant Pro."""
    requested, _ = resolve_tenant(headers, host=host)
    if requested and requested != settings.default_tenant_id:
        access, failure = await fetch_access(client, requested, identity.user_id)
        if access:
            return Decision(
                allowed=True, identity=identity, tenant_id=access["tenant_id"], tenant_slug=access["tenant_slug"],
                tenant_role=access["role"], tenant_tier=access.get("tier"), tenant_quotas=access.get("quotas") or None,
            )
    return Decision(allowed=True, identity=identity, tenant_id=settings.default_tenant_id)


async def authorize(
    *,
    method: str,
    path: str,
    target_url: str,
    headers: dict,
    query_params: dict,
    host: Optional[str],
    body: bytes,
    client: httpx.AsyncClient,
) -> Decision:
    if not safe_path(path):
        return deny(400, "invalid request path")
    cp = canonical_path(path)
    policy = classify(method, cp, service_of(target_url))

    if policy.access is Access.DENY:
        return deny(403, "this endpoint is internal and not available through the gateway")
    if policy.access is Access.PUBLIC:
        return Decision(allowed=True)

    identity, failure = await fetch_identity(client, {k.lower(): v for k, v in headers.items()}.get("cookie"))
    if failure:
        return failure

    if policy.body_user_field:
        try:
            payload = json.loads(body or b"{}")
            claimed = payload.get(policy.body_user_field) if isinstance(payload, dict) else None
        except ValueError:
            return deny(400, "invalid JSON body")
        if str(claimed) != identity.user_id:
            return deny(403, f"{policy.body_user_field} must be the authenticated user")

    if policy.free_tier_only:
        try:
            tier = (json.loads(body or b"{}") or {}).get("tier", "community")
        except (ValueError, AttributeError):
            return deny(400, "invalid JSON body")
        if tier != "community":  # senão qualquer um criaria uma organização Team/Enterprise sem pagar
            return deny(403, "new organizations start on the Free plan; subscribe to Pro through the billing checkout")

    if policy.access is Access.SESSION:
        if policy.soft_tenant:
            return await _soft_tenant(client, identity, headers, host)
        return Decision(allowed=True, identity=identity)
    if policy.access is Access.PLATFORM_ADMIN:
        if identity.role != "admin":
            return deny(403, "platform administrator role required")
        return Decision(allowed=True, identity=identity)

    # --- tenant pedido (NÃO confiável até a checagem abaixo) ---
    if policy.tenant_from == "path":
        requested = policy.path_ref or ""
    elif policy.tenant_from == "query" and query_params.get("tenant_id"):
        requested = query_params["tenant_id"]
    else:
        requested, _ = resolve_tenant(headers, host=host)

    if requested == settings.default_tenant_id:
        # Workspace compartilhado/legado (sem organização): qualquer autenticado usa; administrar exige admin da plataforma.
        if policy.access is Access.ADMIN and identity.role != "admin":
            return deny(403, "administrator role required")
        return Decision(
            allowed=True, identity=identity, tenant_id=requested, tenant_slug=None,
            tenant_role="admin" if identity.role == "admin" else "member",
            query_overrides={"tenant_id": requested} if policy.tenant_from == "query" else {},
        )

    access, failure = await fetch_access(client, requested, identity.user_id)
    if failure:
        return failure
    if policy.access is Access.ADMIN and access["role"] not in ADMIN_TENANT_ROLES:
        return deny(403, "tenant owner/admin role required")
    return Decision(
        allowed=True, identity=identity, tenant_id=access["tenant_id"], tenant_slug=access["tenant_slug"],
        tenant_role=access["role"], tenant_tier=access.get("tier"), tenant_quotas=access.get("quotas") or None,
        query_overrides={"tenant_id": access["tenant_id"]} if policy.tenant_from == "query" else {},
    )
