from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status, Depends
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

store: Optional[TenantStore] = None


def get_store() -> TenantStore:
    global store
    if store is None:
        store = TenantStore(settings.database_url)
    return store


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_store()
    yield


app = FastAPI(
    title="MetaStatistic Auth & Tenant Service",
    version="0.1.0",
    description="Identity, RBAC, and Multi-Tenancy Management for MetaStatistic",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "auth-tenant-service",
        "version": "0.1.0",
    }


# ==========================================
# Tenants Endpoints
# ==========================================


@app.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, tenant_store: TenantStore = Depends(get_store)):
    return tenant_store.create_tenant(payload)


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
):
    try:
        return tenant_store.create_invitation(tenant_id, payload)
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@app.post("/tenants/invitations/{token}/accept", response_model=TenantMemberResponse)
def accept_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    tenant_store: TenantStore = Depends(get_store),
):
    try:
        return tenant_store.accept_invitation(token, payload)
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
):
    try:
        return tenant_store.update_member_role(tenant_id, user_id, payload.role)
    except TenantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.delete("/tenants/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    tenant_id: str,
    user_id: str,
    tenant_store: TenantStore = Depends(get_store),
):
    try:
        removed = tenant_store.remove_member(tenant_id, user_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {user_id} not found in tenant {tenant_id}",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==========================================
# Auth & Token Endpoints
# ==========================================


@app.post("/auth/token", response_model=TokenResponse)
def issue_token(
    payload: LoginRequest,
    tenant_store: TenantStore = Depends(get_store),
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

    # Se for membro ou se o role foi aceito
    token_str = create_access_token(
        user_id=payload.user_id,
        tenant_id=tenant.id,
        role=role,
        tier=tenant.tier,
        secret_key=settings.jwt_secret_key,
        expires_in_minutes=settings.jwt_expire_minutes,
        email=member.email if member else None,
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
