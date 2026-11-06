import base64
import json
import re
from typing import Optional, Tuple
from fastapi import Request
from app.config import settings

RESERVED_SUBDOMAINS = {
    "localhost",
    "127",
    "gateway",
    "api",
    "web",
    "www",
    "app",
    "admin",
    "mail",
    "dev",
    "test",
    "staging",
}


def _b64url_decode(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))


def extract_jwt_tenant_id(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload_bytes = _b64url_decode(parts[1])
        payload = json.loads(payload_bytes.decode("utf-8"))
        return payload.get("tenant_id")
    except Exception:
        return None


def extract_subdomain(host: Optional[str]) -> Optional[str]:
    if not host:
        return None
    # Remove porta se presente (ex: acme.metastatistic.com:8080)
    clean_host = host.split(":")[0].strip().lower()
    
    # Se for IP ou localhost, não há subdomínio de inquilino
    if clean_host in {"localhost", "127.0.0.1", "::1"} or re.match(r"^\d+\.\d+\.\d+\.\d+$", clean_host):
        return None

    parts = clean_host.split(".")
    # Espera pelo menos <subdomain>.<domain>.<tld> (3 partes) ou <subdomain>.localhost (2 partes)
    if len(parts) >= 3:
        sub = parts[0]
        if sub not in RESERVED_SUBDOMAINS:
            return sub
    elif len(parts) == 2 and parts[1] == "localhost":
        sub = parts[0]
        if sub not in RESERVED_SUBDOMAINS:
            return sub

    return None


def resolve_tenant(
    headers: dict,
    host: Optional[str] = None,
    default_tenant: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    Resolve tenant_id e tenant_slug com base em:
    1. Header X-Tenant-ID / X-Tenant-Slug
    2. Subdomínio da requisição (Host: acme.metastatistic.com)
    3. Claim tenant_id no JWT Bearer token
    4. Default tenant_id configurado
    Retorna (tenant_id, tenant_slug).
    """
    default_tenant = default_tenant or settings.default_tenant_id

    # Normaliza headers para minúsculas
    norm_headers = {k.lower(): v for k, v in headers.items()}

    tenant_id_hdr = norm_headers.get("x-tenant-id")
    tenant_slug_hdr = norm_headers.get("x-tenant-slug")

    if tenant_id_hdr:
        return tenant_id_hdr.strip(), tenant_slug_hdr.strip() if tenant_slug_hdr else None

    if tenant_slug_hdr:
        # Quando o slug é fornecido, ele serve como identificador de tenant
        return tenant_slug_hdr.strip(), tenant_slug_hdr.strip()

    # 2. Subdomínio da requisição
    subdomain = extract_subdomain(host or norm_headers.get("host"))
    if subdomain:
        return subdomain, subdomain

    # 3. Bearer JWT
    auth_hdr = norm_headers.get("authorization")
    jwt_tenant_id = extract_jwt_tenant_id(auth_hdr)
    if jwt_tenant_id:
        return jwt_tenant_id, None

    # 4. Default
    return default_tenant, None


async def tenant_middleware(request: Request, call_next):
    host = request.headers.get("host")
    tenant_id, tenant_slug = resolve_tenant(dict(request.headers), host=host)
    
    # Armazena no state da request para acesso direto se necessário
    request.state.tenant_id = tenant_id
    request.state.tenant_slug = tenant_slug

    response = await call_next(request)
    # Garante que a resposta também traga a identificação do tenant resolvido
    response.headers["X-Tenant-ID"] = tenant_id
    if tenant_slug:
        response.headers["X-Tenant-Slug"] = tenant_slug
    return response
