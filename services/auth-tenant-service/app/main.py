from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.jwt_auth import (
    create_access_token,
    decode_access_token,
    InvalidTokenError,
    TokenExpiredError,
)
from app.models import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationResponse,
    LoginRequest,
    MemberRoleUpdate,
    TenantCreate,
    TenantMemberResponse,
    TenantResponse,
    TenantTierUpdate,
    TokenPayload,
    TokenResponse,
    VerifyTokenRequest,
)
from app.tenants import (
    InvitationError,
    QuotaExceededError,
    TenantNotFoundError,
    TenantStore,
)
from app.sso import (
    OIDCCallbackRequest,
    SAMLACSRequest,
    SSOConfigCreate,
    SSOConfigResponse,
    SSOLoginRequest,
    SSOLoginResponse,
    SSOManager,
)
from app.scim import (
    SCIMError,
    SCIMListResponse,
    SCIMManager,
    SCIMPatchRequest,
    SCIMUser,
    SCIMUserCreate,
)
from app.audit_trail import (
    AuditEventCreate,
    AuditEventResponse,
    AuditExportResponse,
    AuditTrailManager,
    AuditVerificationResult,
)

store: Optional[TenantStore] = None


def get_store() -> TenantStore:
    global store
    if store is None:
        store = TenantStore(settings.database_url)
    return store


def get_sso_manager(tenant_store: TenantStore = Depends(get_store)) -> SSOManager:
    return SSOManager(tenant_store)


def get_scim_manager(tenant_store: TenantStore = Depends(get_store)) -> SCIMManager:
    return SCIMManager(tenant_store)


def get_audit_manager(tenant_store: TenantStore = Depends(get_store)) -> AuditTrailManager:
    return AuditTrailManager(tenant_store._get_connection)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()
    yield


app = FastAPI(
    title="MetaStatistic Auth, Tenant & Enterprise Security Service",
    version="1.0.0",
    description="Identity, RBAC, Multi-Tenancy, SAML/OIDC SSO, SCIM 2.0, and SOC 2 / FDA Audit Trail for MetaStatistic",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SCIMError)
async def scim_error_handler(request: Request, exc: SCIMError):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers={"Content-Type": "application/scim+json"},
    )


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "auth-tenant-service",
        "version": "1.0.0",
        "features": ["rbac", "sso_saml", "sso_oidc", "scim_v2", "audit_trail_immutable"],
    }


# ==========================================
# Tenants Endpoints
# ==========================================


@app.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    tenant = tenant_store.create_tenant(payload)
    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant.id,
            user_id=payload.owner_id,
            action="tenant.create",
            resource_type="tenant",
            resource_id=tenant.id,
            details={"tier": tenant.tier, "name": tenant.name, "slug": tenant.slug},
        )
    )
    return tenant


@app.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, tenant_store: TenantStore = Depends(get_store)):
    tenant = tenant_store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    return tenant


@app.get("/tenants/by-slug/{slug}", response_model=TenantResponse)
def get_tenant_by_slug(slug: str, tenant_store: TenantStore = Depends(get_store)):
    tenant = tenant_store.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with slug '{slug}' not found",
        )
    return tenant


@app.patch("/tenants/{tenant_id}/tier", response_model=TenantResponse)
def update_tenant_tier(
    tenant_id: str,
    payload: TenantTierUpdate,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        tenant = tenant_store.update_tenant_tier(tenant_id, payload.tier)
    except TenantNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant.id,
            user_id="system:billing",
            action="tenant.tier_updated",
            resource_type="tenant",
            resource_id=tenant.id,
            details={"new_tier": tenant.tier, "quotas": tenant.quotas},
        )
    )
    return tenant


# ==========================================
# Invitations Endpoints
# ==========================================


@app.post(
    "/tenants/{tenant_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    tenant_id: str,
    payload: InvitationCreate,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        inv = tenant_store.create_invitation(tenant_id, payload)
        audit.record_event(
            AuditEventCreate(
                tenant_id=tenant_id,
                user_id="admin",
                action="invitation.create",
                resource_type="invitation",
                resource_id=inv.id,
                details={"email": inv.email, "role": inv.role},
            )
        )
        return inv
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@app.post("/tenants/invitations/{token}/accept", response_model=TenantMemberResponse)
def accept_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        member = tenant_store.accept_invitation(token, payload)
        # Busca tenant do membro
        audit.record_event(
            AuditEventCreate(
                tenant_id="tenant",
                user_id=member.user_id,
                action="invitation.accept",
                resource_type="tenant_member",
                resource_id=member.user_id,
                details={"email": member.email, "role": member.role},
            )
        )
        return member
    except InvitationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ==========================================
# Tenant Members Endpoints
# ==========================================


@app.get("/tenants/{tenant_id}/members", response_model=List[TenantMemberResponse])
def list_members(tenant_id: str, tenant_store: TenantStore = Depends(get_store)):
    tenant = tenant_store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    return tenant_store.list_members(tenant_id)


@app.patch("/tenants/{tenant_id}/members/{user_id}", response_model=TenantMemberResponse)
def update_member_role(
    tenant_id: str,
    user_id: str,
    payload: MemberRoleUpdate,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        member = tenant_store.update_member_role(tenant_id, user_id, payload.role)
        audit.record_event(
            AuditEventCreate(
                tenant_id=tenant_id,
                user_id=user_id,
                action="member.role_update",
                resource_type="tenant_member",
                resource_id=user_id,
                details={"new_role": payload.role},
            )
        )
        return member
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/tenants/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    tenant_id: str,
    user_id: str,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        removed = tenant_store.remove_member(tenant_id, user_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {user_id} not found in tenant {tenant_id}",
            )
        audit.record_event(
            AuditEventCreate(
                tenant_id=tenant_id,
                user_id=user_id,
                action="member.remove",
                resource_type="tenant_member",
                resource_id=user_id,
                details={"removed_user": user_id},
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==========================================
# Auth & Token Endpoints
# ==========================================


@app.get("/auth/status")
def auth_status() -> Dict[str, Any]:
    """
    Retorna o status de autenticação padrão para compatibilidade com o frontend.
    """
    return {
        "auth_enabled": False,
        "needs_setup": False,
        "user": {
            "id": "anonymous",
            "username": "anonymous",
            "display_name": "Administrador",
            "role": "admin",
        },
    }


@app.post("/auth/token", response_model=TokenResponse)
def issue_token(
    payload: LoginRequest,
    tenant_store: TenantStore = Depends(get_store),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    tenant = None
    if payload.tenant_id:
        tenant = tenant_store.get_tenant(payload.tenant_id)
    elif payload.tenant_slug:
        tenant = tenant_store.get_tenant_by_slug(payload.tenant_slug)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid tenant_id or tenant_slug is required to issue a token",
        )

    # Verifica se o usuário é membro do tenant
    member = tenant_store.get_member(tenant.id, payload.user_id)
    role = payload.role or (member.role if member else "viewer")

    token_str = create_access_token(
        user_id=payload.user_id,
        tenant_id=tenant.id,
        role=role,
        tier=tenant.tier,
        secret_key=settings.jwt_secret_key,
        expires_in_minutes=settings.jwt_expire_minutes,
        email=member.email if member else None,
    )

    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant.id,
            user_id=payload.user_id,
            action="auth.token_issued",
            resource_type="auth_token",
            resource_id=payload.user_id,
            details={"role": role, "tier": tenant.tier},
        )
    )

    return TokenResponse(
        access_token=token_str,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        tenant_id=tenant.id,
        role=role,
        tier=tenant.tier,
    )


@app.post("/auth/verify", response_model=TokenPayload)
def verify_token(payload: VerifyTokenRequest):
    try:
        decoded = decode_access_token(payload.token, settings.jwt_secret_key)
        return decoded
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired: {e}",
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


# ==========================================
# Enterprise SSO Endpoints (SAML 2.0 & OIDC)
# ==========================================


@app.post("/tenants/{tenant_id}/sso/config", response_model=SSOConfigResponse)
def set_tenant_sso_config(
    tenant_id: str,
    payload: SSOConfigCreate,
    sso: SSOManager = Depends(get_sso_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        resp = sso.set_config(tenant_id, payload)
        audit.record_event(
            AuditEventCreate(
                tenant_id=tenant_id,
                user_id="admin",
                action="sso.config_update",
                resource_type="sso_config",
                resource_id=tenant_id,
                details={"provider_type": payload.provider_type, "enabled": payload.enabled},
            )
        )
        return resp
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/tenants/{tenant_id}/sso/config", response_model=SSOConfigResponse)
def get_tenant_sso_config(
    tenant_id: str,
    sso: SSOManager = Depends(get_sso_manager),
):
    cfg = sso.get_config(tenant_id)
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSO configuration not found for tenant {tenant_id}",
        )
    return cfg


@app.post("/auth/sso/login", response_model=SSOLoginResponse)
def sso_login(
    payload: SSOLoginRequest,
    sso: SSOManager = Depends(get_sso_manager),
):
    try:
        return sso.initiate_sso_login(payload)
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/auth/sso/saml/acs", response_model=TokenResponse)
def saml_acs_endpoint(
    payload: SAMLACSRequest,
    sso: SSOManager = Depends(get_sso_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        resp = sso.process_saml_assertion(
            payload=payload,
            jwt_secret_key=settings.jwt_secret_key,
            jwt_expire_minutes=settings.jwt_expire_minutes,
        )
        audit.record_event(
            AuditEventCreate(
                tenant_id=resp.tenant_id,
                user_id="sso_user",
                action="sso.saml_login_success",
                resource_type="auth_session",
                resource_id=resp.tenant_id,
                details={"role": resp.role, "provider": "saml2"},
            )
        )
        return resp
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/auth/sso/oidc/callback", response_model=TokenResponse)
def oidc_callback_endpoint(
    payload: OIDCCallbackRequest,
    sso: SSOManager = Depends(get_sso_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    try:
        resp = sso.process_oidc_callback(
            payload=payload,
            jwt_secret_key=settings.jwt_secret_key,
            jwt_expire_minutes=settings.jwt_expire_minutes,
        )
        audit.record_event(
            AuditEventCreate(
                tenant_id=resp.tenant_id,
                user_id="sso_oidc_user",
                action="sso.oidc_login_success",
                resource_type="auth_session",
                resource_id=resp.tenant_id,
                details={"role": resp.role, "provider": "oidc"},
            )
        )
        return resp
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==========================================
# SCIM 2.0 Provisioning Endpoints (RFC 7643 / RFC 7644)
# ==========================================


@app.get("/scim/v2/tenants/{tenant_id}/ServiceProviderConfig")
def scim_service_provider_config(
    tenant_id: str,
    request: Request,
    scim: SCIMManager = Depends(get_scim_manager),
):
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        content=scim.get_service_provider_config(tenant_id, base_url),
        headers={"Content-Type": "application/scim+json"},
    )


@app.get("/scim/v2/tenants/{tenant_id}/Schemas")
def scim_schemas(
    tenant_id: str,
    request: Request,
    scim: SCIMManager = Depends(get_scim_manager),
):
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        content=scim.get_schemas(tenant_id, base_url),
        headers={"Content-Type": "application/scim+json"},
    )


@app.get("/scim/v2/tenants/{tenant_id}/Users", response_model=SCIMListResponse)
def scim_list_users(
    tenant_id: str,
    request: Request,
    filter: Optional[str] = None,
    startIndex: int = 1,
    count: int = 100,
    scim: SCIMManager = Depends(get_scim_manager),
):
    base_url = str(request.base_url).rstrip("/")
    res = scim.list_users(
        tenant_id=tenant_id,
        base_url=base_url,
        filter_expr=filter,
        start_index=startIndex,
        count=count,
    )
    return JSONResponse(
        content=res.model_dump(),
        headers={"Content-Type": "application/scim+json"},
    )


@app.post("/scim/v2/tenants/{tenant_id}/Users", response_model=SCIMUser, status_code=status.HTTP_201_CREATED)
def scim_create_user(
    tenant_id: str,
    payload: SCIMUserCreate,
    request: Request,
    scim: SCIMManager = Depends(get_scim_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    base_url = str(request.base_url).rstrip("/")
    user = scim.create_user(tenant_id, base_url, payload)
    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant_id,
            user_id="scim_idp",
            action="scim.user_provisioned",
            resource_type="scim_user",
            resource_id=user.id,
            details={"userName": user.userName},
        )
    )
    return JSONResponse(
        content=user.model_dump(),
        status_code=status.HTTP_201_CREATED,
        headers={
            "Content-Type": "application/scim+json",
            "Location": user.meta.location,
        },
    )


@app.get("/scim/v2/tenants/{tenant_id}/Users/{user_id}", response_model=SCIMUser)
def scim_get_user(
    tenant_id: str,
    user_id: str,
    request: Request,
    scim: SCIMManager = Depends(get_scim_manager),
):
    base_url = str(request.base_url).rstrip("/")
    user = scim.get_user(tenant_id, user_id, base_url)
    return JSONResponse(
        content=user.model_dump(),
        headers={"Content-Type": "application/scim+json"},
    )


@app.patch("/scim/v2/tenants/{tenant_id}/Users/{user_id}", response_model=SCIMUser)
def scim_patch_user(
    tenant_id: str,
    user_id: str,
    payload: SCIMPatchRequest,
    request: Request,
    scim: SCIMManager = Depends(get_scim_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    base_url = str(request.base_url).rstrip("/")
    updated = scim.patch_user(tenant_id, user_id, base_url, payload)
    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant_id,
            user_id="scim_idp",
            action="scim.user_patched",
            resource_type="scim_user",
            resource_id=user_id,
            details={"active": updated.active},
        )
    )
    return JSONResponse(
        content=updated.model_dump(),
        headers={"Content-Type": "application/scim+json"},
    )


@app.delete("/scim/v2/tenants/{tenant_id}/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def scim_delete_user(
    tenant_id: str,
    user_id: str,
    scim: SCIMManager = Depends(get_scim_manager),
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    scim.delete_user(tenant_id, user_id)
    audit.record_event(
        AuditEventCreate(
            tenant_id=tenant_id,
            user_id="scim_idp",
            action="scim.user_deprovisioned",
            resource_type="scim_user",
            resource_id=user_id,
            details={"deleted_user": user_id},
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==========================================
# Immutable Audit Trail Endpoints (SOC 2 Type II / FDA 21 CFR Part 11)
# ==========================================


@app.post("/audit/events", response_model=AuditEventResponse, status_code=status.HTTP_201_CREATED)
def record_audit_event(
    payload: AuditEventCreate,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    return audit.record_event(payload)


@app.get("/audit/events", response_model=List[AuditEventResponse])
def list_audit_events(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    return audit.list_events(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        limit=limit,
        offset=offset,
    )


@app.get("/audit/verify", response_model=AuditVerificationResult)
def verify_audit_trail(
    tenant_id: Optional[str] = None,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    """
    Executa a verificação matemática de integridade criptográfica da cadeia de hashes (Merkle/SHA-256).
    Comprova que não houve nenhuma adulteração no banco de dados.
    """
    return audit.verify_integrity(tenant_id=tenant_id)


@app.get("/audit/export", response_model=AuditExportResponse)
def export_audit_trail(
    tenant_id: Optional[str] = None,
    audit: AuditTrailManager = Depends(get_audit_manager),
):
    """
    Exporta a trilha de auditoria completa com atestado de integridade e metadados de conformidade.
    """
    return audit.export_audit_trail(tenant_id=tenant_id)
