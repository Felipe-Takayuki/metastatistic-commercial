import base64
import json
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, Field

from app.jwt_auth import create_access_token
from app.models import RoleType, TokenResponse
from app.tenants import QuotaExceededError, TenantNotFoundError, TenantStore

SSOProviderType = Literal["saml", "oidc"]


class SSOConfigCreate(BaseModel):
    provider_type: SSOProviderType = "saml"
    enabled: bool = True
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_cert: Optional[str] = None
    sp_entity_id: Optional[str] = "https://metastatistic.com/saml/metadata"
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_auth_url: Optional[str] = None
    oidc_token_url: Optional[str] = None
    oidc_userinfo_url: Optional[str] = None
    jit_provisioning: bool = True
    default_role: RoleType = "analyst"
    attribute_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "email": "email",
            "name": "name",
            "role": "role",
        }
    )


class SSOConfigResponse(SSOConfigCreate):
    tenant_id: str
    updated_at: str


class SSOLoginRequest(BaseModel):
    tenant_id: Optional[str] = None
    tenant_slug: Optional[str] = None
    redirect_url: Optional[str] = None


class SSOLoginResponse(BaseModel):
    auth_url: str
    provider_type: SSOProviderType
    saml_request: Optional[str] = None
    relay_state: Optional[str] = None
    state: Optional[str] = None


class SAMLACSRequest(BaseModel):
    SAMLResponse: str = Field(..., description="Base64 encoded SAML Response XML from IdP")
    RelayState: Optional[str] = None
    tenant_id: Optional[str] = None


class OIDCCallbackRequest(BaseModel):
    code: str
    tenant_id: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = None


def generate_saml_authn_request_xml(
    request_id: str,
    sp_entity_id: str,
    idp_sso_url: str,
    acs_url: str,
) -> str:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                    ID="{request_id}"
                    Version="2.0"
                    IssueInstant="{now_iso}"
                    Destination="{idp_sso_url}"
                    AssertionConsumerServiceURL="{acs_url}"
                    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>{sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
                        AllowCreate="true"/>
</samlp:AuthnRequest>"""
    return xml_str


def parse_saml_response_xml(xml_content: str) -> Dict[str, Any]:
    """
    Parse seguro de SAML Response XML sem resolução de entidades externas.
    Extrai Subject (NameID), status e atributos (email, displayName, roles).
    """
    root = ET.fromstring(xml_content)

    # Namespaces comuns de SAML
    ns = {
        "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
        "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    }

    # Verifica status
    status_code = None
    for elem in root.iter():
        if elem.tag.endswith("StatusCode"):
            status_code = elem.attrib.get("Value", "")
            break

    if status_code and not status_code.endswith(":Success"):
        raise ValueError(f"SAML IdP returned error status: {status_code}")

    # Extrai NameID
    name_id = None
    for elem in root.iter():
        if elem.tag.endswith("NameID"):
            name_id = elem.text.strip() if elem.text else None
            break

    # Extrai Atributos
    attributes: Dict[str, Any] = {}
    for attr_elem in root.iter():
        if attr_elem.tag.endswith("Attribute"):
            attr_name = attr_elem.attrib.get("Name") or attr_elem.attrib.get("FriendlyName")
            if not attr_name:
                continue
            values = []
            for val_elem in attr_elem:
                if val_elem.tag.endswith("AttributeValue") and val_elem.text:
                    values.append(val_elem.text.strip())
            if len(values) == 1:
                attributes[attr_name] = values[0]
            elif len(values) > 1:
                attributes[attr_name] = values

    # Normaliza email
    email = attributes.get("email") or attributes.get("User.Email") or attributes.get("mail") or name_id
    if not email:
        raise ValueError("Could not extract user email/NameID from SAML Assertion")

    first_name = attributes.get("firstName") or attributes.get("first_name") or ""
    last_name = attributes.get("lastName") or attributes.get("last_name") or ""
    name = (
        attributes.get("displayName")
        or attributes.get("name")
        or (f"{first_name} {last_name}".strip() if (first_name or last_name) else email.split("@")[0])
    )
    role = attributes.get("role") or attributes.get("roles") or attributes.get("groups")

    return {
        "email": email,
        "name": name,
        "name_id": name_id,
        "role": role,
        "raw_attributes": attributes,
    }


class SSOManager:
    def __init__(self, tenant_store: TenantStore):
        self.tenant_store = tenant_store
        self._init_table()

    def _init_table(self):
        with self.tenant_store._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenant_sso_configs (
                    tenant_id TEXT PRIMARY KEY,
                    provider_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    idp_entity_id TEXT,
                    idp_sso_url TEXT,
                    idp_cert TEXT,
                    sp_entity_id TEXT,
                    oidc_issuer TEXT,
                    oidc_client_id TEXT,
                    oidc_client_secret TEXT,
                    oidc_auth_url TEXT,
                    oidc_token_url TEXT,
                    oidc_userinfo_url TEXT,
                    jit_provisioning INTEGER NOT NULL DEFAULT 1,
                    default_role TEXT NOT NULL DEFAULT 'analyst',
                    attribute_mapping TEXT DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                );
            """)

    def set_config(self, tenant_id: str, config: SSOConfigCreate) -> SSOConfigResponse:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        now_iso = datetime.now(timezone.utc).isoformat()
        attr_json = json.dumps(config.attribute_mapping)

        with self.tenant_store._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tenant_sso_configs (
                    tenant_id, provider_type, enabled, idp_entity_id, idp_sso_url, idp_cert,
                    sp_entity_id, oidc_issuer, oidc_client_id, oidc_client_secret,
                    oidc_auth_url, oidc_token_url, oidc_userinfo_url, jit_provisioning,
                    default_role, attribute_mapping, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    provider_type = excluded.provider_type,
                    enabled = excluded.enabled,
                    idp_entity_id = excluded.idp_entity_id,
                    idp_sso_url = excluded.idp_sso_url,
                    idp_cert = excluded.idp_cert,
                    sp_entity_id = excluded.sp_entity_id,
                    oidc_issuer = excluded.oidc_issuer,
                    oidc_client_id = excluded.oidc_client_id,
                    oidc_client_secret = excluded.oidc_client_secret,
                    oidc_auth_url = excluded.oidc_auth_url,
                    oidc_token_url = excluded.oidc_token_url,
                    oidc_userinfo_url = excluded.oidc_userinfo_url,
                    jit_provisioning = excluded.jit_provisioning,
                    default_role = excluded.default_role,
                    attribute_mapping = excluded.attribute_mapping,
                    updated_at = excluded.updated_at
                """,
                (
                    tenant_id,
                    config.provider_type,
                    1 if config.enabled else 0,
                    config.idp_entity_id,
                    config.idp_sso_url,
                    config.idp_cert,
                    config.sp_entity_id,
                    config.oidc_issuer,
                    config.oidc_client_id,
                    config.oidc_client_secret,
                    config.oidc_auth_url,
                    config.oidc_token_url,
                    config.oidc_userinfo_url,
                    1 if config.jit_provisioning else 0,
                    config.default_role,
                    attr_json,
                    now_iso,
                ),
            )
            conn.commit()

        return self.get_config(tenant_id)

    def get_config(self, tenant_id: str) -> Optional[SSOConfigResponse]:
        with self.tenant_store._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_sso_configs WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if not row:
                return None

            try:
                attr_mapping = json.loads(row["attribute_mapping"]) if row["attribute_mapping"] else {}
            except Exception:
                attr_mapping = {}

            return SSOConfigResponse(
                tenant_id=row["tenant_id"],
                provider_type=row["provider_type"],
                enabled=bool(row["enabled"]),
                idp_entity_id=row["idp_entity_id"],
                idp_sso_url=row["idp_sso_url"],
                idp_cert=row["idp_cert"],
                sp_entity_id=row["sp_entity_id"],
                oidc_issuer=row["oidc_issuer"],
                oidc_client_id=row["oidc_client_id"],
                oidc_client_secret=row["oidc_client_secret"],
                oidc_auth_url=row["oidc_auth_url"],
                oidc_token_url=row["oidc_token_url"],
                oidc_userinfo_url=row["oidc_userinfo_url"],
                jit_provisioning=bool(row["jit_provisioning"]),
                default_role=row["default_role"],
                attribute_mapping=attr_mapping,
                updated_at=row["updated_at"],
            )

    def initiate_sso_login(self, payload: SSOLoginRequest, base_url: str = "https://metastatistic.com") -> SSOLoginResponse:
        tenant = None
        if payload.tenant_id:
            tenant = self.tenant_store.get_tenant(payload.tenant_id)
        elif payload.tenant_slug:
            tenant = self.tenant_store.get_tenant_by_slug(payload.tenant_slug)

        if not tenant:
            raise TenantNotFoundError("Valid tenant_id or tenant_slug is required for SSO")

        config = self.get_config(tenant.id)
        if not config or not config.enabled:
            raise ValueError(f"SSO is not enabled or configured for tenant '{tenant.name}'")

        if config.provider_type == "saml":
            req_id = f"ID_{uuid.uuid4().hex}"
            acs_url = f"{base_url.rstrip('/')}/auth/sso/saml/acs"
            sp_entity_id = config.sp_entity_id or f"{base_url.rstrip('/')}/saml/metadata"
            xml_req = generate_saml_authn_request_xml(
                request_id=req_id,
                sp_entity_id=sp_entity_id,
                idp_sso_url=config.idp_sso_url or "https://idp.example.com/sso",
                acs_url=acs_url,
            )
            saml_b64 = base64.b64encode(xml_req.encode("utf-8")).decode("ascii")
            relay_state = payload.redirect_url or f"tenant:{tenant.id}"
            
            # Constrói URL de redirect HTTP-Redirect binding
            params = {
                "SAMLRequest": saml_b64,
                "RelayState": relay_state,
            }
            auth_url = f"{config.idp_sso_url}?{urlencode(params)}"
            return SSOLoginResponse(
                auth_url=auth_url,
                provider_type="saml",
                saml_request=saml_b64,
                relay_state=relay_state,
            )

        elif config.provider_type == "oidc":
            state = f"{tenant.id}:{uuid.uuid4().hex}"
            redirect_uri = f"{base_url.rstrip('/')}/auth/sso/oidc/callback"
            params = {
                "client_id": config.oidc_client_id or "metastatistic-client",
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": redirect_uri,
                "state": state,
            }
            auth_url = f"{config.oidc_auth_url or 'https://accounts.google.com/o/oauth2/v2/auth'}?{urlencode(params)}"
            return SSOLoginResponse(
                auth_url=auth_url,
                provider_type="oidc",
                state=state,
            )
        else:
            raise ValueError(f"Unsupported SSO provider: {config.provider_type}")

    def provision_jit_user(
        self,
        tenant_id: str,
        email: str,
        suggested_role: Optional[str] = None,
        config: Optional[SSOConfigResponse] = None,
    ) -> Dict[str, Any]:
        """
        Provisiona o usuário Just-In-Time se ainda não for membro.
        """
        if not config:
            config = self.get_config(tenant_id)

        target_role = suggested_role if suggested_role in {"owner", "admin", "statistician", "analyst", "viewer"} else None
        if not target_role:
            target_role = config.default_role if config else "analyst"

        with self.tenant_store._get_connection() as conn:
            # Procura se já existe membro por email ou user_id
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND email = ?",
                (tenant_id, email),
            ).fetchone()

            if existing:
                return {
                    "user_id": existing["user_id"],
                    "email": existing["email"],
                    "role": existing["role"],
                    "provisioned": False,
                }

            # Se não existe e JIT estiver habilitado
            if not config or not config.jit_provisioning:
                raise ValueError(f"User {email} is not enrolled and JIT provisioning is disabled")

            # Checa cota de usuários
            tenant = self.tenant_store.get_tenant(tenant_id)
            if not tenant:
                raise TenantNotFoundError(f"Tenant {tenant_id} not found")

            tier_quota = tenant.quotas.get("max_users", 1000)
            current_count = self.tenant_store.count_effective_users(tenant_id)
            if current_count >= tier_quota:
                raise QuotaExceededError(
                    f"Tenant user quota ({tier_quota}) exceeded for tier '{tenant.tier}'"
                )

            user_id = f"sso_{uuid.uuid4().hex[:12]}"
            now_iso = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO tenant_members (tenant_id, user_id, email, role, joined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tenant_id, user_id, email, target_role, now_iso),
            )
            conn.commit()

            return {
                "user_id": user_id,
                "email": email,
                "role": target_role,
                "provisioned": True,
            }

    def process_saml_assertion(
        self,
        payload: SAMLACSRequest,
        jwt_secret_key: str,
        jwt_expire_minutes: int = 1440,
    ) -> TokenResponse:
        # Decodifica resposta SAML
        try:
            xml_bytes = base64.b64decode(payload.SAMLResponse)
            xml_content = xml_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Invalid Base64 encoded SAMLResponse: {e}")

        parsed = parse_saml_response_xml(xml_content)
        email = parsed["email"]

        # Identifica tenant_id
        tenant_id = payload.tenant_id
        if not tenant_id and payload.RelayState and "tenant:" in payload.RelayState:
            tenant_id = payload.RelayState.split("tenant:")[1].split("&")[0].split("/")[0]

        if not tenant_id:
            raise ValueError("Tenant ID could not be identified from SAML request/RelayState")

        config = self.get_config(tenant_id)
        if not config:
            raise ValueError(f"SSO configuration not found for tenant {tenant_id}")

        member_info = self.provision_jit_user(
            tenant_id=tenant_id,
            email=email,
            suggested_role=parsed.get("role"),
            config=config,
        )

        tenant = self.tenant_store.get_tenant(tenant_id)
        token_str = create_access_token(
            user_id=member_info["user_id"],
            tenant_id=tenant_id,
            role=member_info["role"],
            tier=tenant.tier if tenant else "enterprise",
            secret_key=jwt_secret_key,
            expires_in_minutes=jwt_expire_minutes,
            email=email,
        )

        return TokenResponse(
            access_token=token_str,
            token_type="bearer",
            expires_in=jwt_expire_minutes * 60,
            tenant_id=tenant_id,
            role=member_info["role"],
            tier=tenant.tier if tenant else "enterprise",
        )

    def process_oidc_callback(
        self,
        payload: OIDCCallbackRequest,
        jwt_secret_key: str,
        jwt_expire_minutes: int = 1440,
    ) -> TokenResponse:
        tenant_id = payload.tenant_id
        config = self.get_config(tenant_id)
        if not config or not config.enabled:
            raise ValueError(f"SSO OIDC not enabled for tenant {tenant_id}")

        # Em ambiente Enterprise / Testes, decodifica código ou gera claims
        # Se code tiver formato mock "sub:email@domain.com", usa diretamente
        email = f"user_{payload.code[:8]}@enterprise.corp"
        if ":" in payload.code and "@" in payload.code:
            email = payload.code.split(":")[-1]

        member_info = self.provision_jit_user(
            tenant_id=tenant_id,
            email=email,
            suggested_role=config.default_role,
            config=config,
        )

        tenant = self.tenant_store.get_tenant(tenant_id)
        token_str = create_access_token(
            user_id=member_info["user_id"],
            tenant_id=tenant_id,
            role=member_info["role"],
            tier=tenant.tier if tenant else "enterprise",
            secret_key=jwt_secret_key,
            expires_in_minutes=jwt_expire_minutes,
            email=email,
        )

        return TokenResponse(
            access_token=token_str,
            token_type="bearer",
            expires_in=jwt_expire_minutes * 60,
            tenant_id=tenant_id,
            role=member_info["role"],
            tier=tenant.tier if tenant else "enterprise",
        )
