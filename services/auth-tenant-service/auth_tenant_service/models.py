from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


TierType = Literal["community", "team", "enterprise"]
RoleType = Literal["owner", "admin", "statistician", "analyst", "viewer"]


class TenantQuotas(BaseModel):
    max_users: int
    max_datasets: int
    max_storage_mb: int
    features: List[str]
    rate_limit_per_min: int


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(None, min_length=2, max_length=60)
    tier: TierType = "community"
    owner_id: str = Field(..., min_length=1)
    owner_email: Optional[str] = None


class TenantTierUpdate(BaseModel):
    tier: TierType


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    tier: TierType
    status: str = "active"
    created_at: str
    quotas: Dict[str, Any]
    members_count: int = 1


class TenantMemberResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    role: RoleType
    joined_at: str


class TenantAccessResponse(BaseModel):
    """Resultado da checagem de associação usada pelo gateway (endpoint interno)."""
    tenant_id: str
    tenant_slug: str
    tier: str
    role: RoleType
    quotas: Dict[str, Any] = {}  # cotas do plano do tenant; o gateway as repassa à API


class MemberRoleUpdate(BaseModel):
    role: RoleType


class InvitationCreate(BaseModel):
    email: str
    role: RoleType = "analyst"
    expires_in_hours: int = Field(72, ge=1, le=720)


class InvitationResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    role: RoleType
    token: str
    created_at: str
    expires_at: str
    accepted: bool = False


class AcceptInvitationRequest(BaseModel):
    user_id: str
    email: Optional[str] = None


class TokenPayload(BaseModel):
    sub: str  # user_id
    tenant_id: str
    role: RoleType
    tier: TierType
    exp: int
    iat: Optional[int] = None
    email: Optional[str] = None


class LoginRequest(BaseModel):
    user_id: str
    tenant_id: Optional[str] = None
    tenant_slug: Optional[str] = None
    role: Optional[RoleType] = None
    password: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: str
    role: RoleType
    tier: TierType


class VerifyTokenRequest(BaseModel):
    token: str
