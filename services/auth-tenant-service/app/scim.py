import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.models import RoleType
from app.tenants import QuotaExceededError, TenantNotFoundError, TenantStore

CORE_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SERVICE_PROVIDER_CONFIG_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class SCIMName(BaseModel):
    formatted: Optional[str] = None
    familyName: Optional[str] = None
    givenName: Optional[str] = None


class SCIMEmail(BaseModel):
    value: str
    type: str = "work"
    primary: bool = True


class SCIMRole(BaseModel):
    value: str
    primary: bool = True


class SCIMMeta(BaseModel):
    resourceType: str = "User"
    created: str
    lastModified: str
    location: str


class SCIMUser(BaseModel):
    schemas: List[str] = [CORE_USER_SCHEMA]
    id: str
    userName: str
    name: Optional[SCIMName] = None
    displayName: Optional[str] = None
    emails: List[SCIMEmail] = []
    roles: List[SCIMRole] = []
    active: bool = True
    meta: SCIMMeta


class SCIMUserCreate(BaseModel):
    schemas: Optional[List[str]] = None
    userName: str
    name: Optional[SCIMName] = None
    displayName: Optional[str] = None
    emails: Optional[List[SCIMEmail]] = None
    roles: Optional[List[Union[SCIMRole, str]]] = None
    active: bool = True


class SCIMPatchOperation(BaseModel):
    op: str = Field(..., description="add, replace, or remove")
    path: Optional[str] = None
    value: Any


class SCIMPatchRequest(BaseModel):
    schemas: Optional[List[str]] = None
    Operations: List[SCIMPatchOperation]


class SCIMListResponse(BaseModel):
    schemas: List[str] = [LIST_RESPONSE_SCHEMA]
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: List[SCIMUser]


class SCIMError(Exception):
    def __init__(self, status_code: int, scim_type: Optional[str], detail: str):
        self.status_code = status_code
        self.scim_type = scim_type
        self.detail = detail
        super().__init__(detail)

    def to_dict(self) -> Dict[str, Any]:
        resp = {
            "schemas": [ERROR_SCHEMA],
            "status": str(self.status_code),
            "detail": self.detail,
        }
        if self.scim_type:
            resp["scimType"] = self.scim_type
        return resp


class SCIMManager:
    def __init__(self, tenant_store: TenantStore):
        self.tenant_store = tenant_store

    def get_service_provider_config(self, tenant_id: str, base_url: str) -> Dict[str, Any]:
        return {
            "schemas": [SERVICE_PROVIDER_CONFIG_SCHEMA],
            "documentationUri": "https://metastatistic.com/docs/scim/v2",
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 200},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "name": "OAuth Bearer Token",
                    "description": "Authentication scheme using OAuth Bearer Token",
                    "specUri": "https://tools.ietf.org/html/rfc6750",
                    "type": "oauthbearertoken",
                    "primary": True,
                }
            ],
            "meta": {
                "resourceType": "ServiceProviderConfig",
                "location": f"{base_url.rstrip('/')}/scim/v2/tenants/{tenant_id}/ServiceProviderConfig",
            },
        }

    def get_schemas(self, tenant_id: str, base_url: str) -> Dict[str, Any]:
        return {
            "schemas": [LIST_RESPONSE_SCHEMA],
            "totalResults": 1,
            "itemsPerPage": 1,
            "startIndex": 1,
            "Resources": [
                {
                    "id": CORE_USER_SCHEMA,
                    "name": "User",
                    "description": "User Account Schema for MetaStatistic Commercial",
                    "attributes": [
                        {"name": "userName", "type": "string", "required": True},
                        {"name": "name", "type": "complex", "required": False},
                        {"name": "emails", "type": "complex", "multiValued": True, "required": True},
                        {"name": "roles", "type": "complex", "multiValued": True, "required": False},
                        {"name": "active", "type": "boolean", "required": False},
                    ],
                    "meta": {
                        "resourceType": "Schema",
                        "location": f"{base_url.rstrip('/')}/scim/v2/tenants/{tenant_id}/Schemas/{CORE_USER_SCHEMA}",
                    },
                }
            ],
        }

    def _member_to_scim_user(self, member_row: sqlite3.Row, tenant_id: str, base_url: str) -> SCIMUser:
        user_id = member_row["user_id"]
        email = member_row["email"] or f"{user_id}@metastatistic.internal"
        role = member_row["role"]
        joined_at = member_row["joined_at"]

        # Verifica se há coluna status ou se está ativo
        is_active = True
        try:
            if "status" in member_row.keys() and member_row["status"] == "inactive":
                is_active = False
        except Exception:
            pass

        return SCIMUser(
            schemas=[CORE_USER_SCHEMA],
            id=user_id,
            userName=email,
            displayName=email.split("@")[0],
            name=SCIMName(formatted=email.split("@")[0], givenName=email.split("@")[0]),
            emails=[SCIMEmail(value=email, type="work", primary=True)],
            roles=[SCIMRole(value=role, primary=True)],
            active=is_active,
            meta=SCIMMeta(
                resourceType="User",
                created=joined_at,
                lastModified=joined_at,
                location=f"{base_url.rstrip('/')}/scim/v2/tenants/{tenant_id}/Users/{user_id}",
            ),
        )

    def list_users(
        self,
        tenant_id: str,
        base_url: str,
        filter_expr: Optional[str] = None,
        start_index: int = 1,
        count: int = 100,
    ) -> SCIMListResponse:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise SCIMError(404, None, f"Tenant {tenant_id} not found")

        with self.tenant_store._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? ORDER BY joined_at ASC",
                (tenant_id,),
            ).fetchall()

        all_users = [self._member_to_scim_user(r, tenant_id, base_url) for r in rows]

        # Filtro básico SCIM: userName eq "email" ou active eq true/false
        if filter_expr:
            match_email = re.search(r'userName\s+eq\s+["\']([^"\']+)["\']', filter_expr, re.IGNORECASE)
            if match_email:
                target_email = match_email.group(1).lower()
                all_users = [u for u in all_users if u.userName.lower() == target_email]

            match_active = re.search(r'active\s+eq\s+(true|false)', filter_expr, re.IGNORECASE)
            if match_active:
                target_active = match_active.group(1).lower() == "true"
                all_users = [u for u in all_users if u.active == target_active]

        total_results = len(all_users)
        start = max(1, start_index) - 1
        page_users = all_users[start : start + count]

        return SCIMListResponse(
            schemas=[LIST_RESPONSE_SCHEMA],
            totalResults=total_results,
            startIndex=start_index,
            itemsPerPage=len(page_users),
            Resources=page_users,
        )

    def get_user(self, tenant_id: str, user_id: str, base_url: str) -> SCIMUser:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise SCIMError(404, None, f"Tenant {tenant_id} not found")

        with self.tenant_store._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()

        if not row:
            raise SCIMError(404, None, f"SCIM User {user_id} not found in tenant {tenant_id}")

        return self._member_to_scim_user(row, tenant_id, base_url)

    def create_user(self, tenant_id: str, base_url: str, payload: SCIMUserCreate) -> SCIMUser:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise SCIMError(404, None, f"Tenant {tenant_id} not found")

        email = payload.userName
        if payload.emails and len(payload.emails) > 0:
            email = payload.emails[0].value

        # Role
        role = "analyst"
        if payload.roles and len(payload.roles) > 0:
            r_val = payload.roles[0]
            role_candidate = r_val.value if isinstance(r_val, SCIMRole) else str(r_val)
            if role_candidate in {"owner", "admin", "statistician", "analyst", "viewer"}:
                role = role_candidate

        with self.tenant_store._get_connection() as conn:
            # Checa se já existe usuário com esse email no tenant
            existing = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND email = ?",
                (tenant_id, email),
            ).fetchone()
            if existing:
                raise SCIMError(409, "uniqueness", f"User with userName/email '{email}' already exists")

            # Checa cota
            tier_quota = tenant.quotas.get("max_users", 1000)
            current_users = self.tenant_store.count_effective_users(tenant_id)
            if current_users >= tier_quota:
                raise SCIMError(
                    403,
                    None,
                    f"Tenant user quota ({tier_quota}) exceeded for tier '{tenant.tier}'",
                )

            user_id = f"scim_{uuid.uuid4().hex[:12]}"
            now_iso = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """
                INSERT INTO tenant_members (tenant_id, user_id, email, role, joined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tenant_id, user_id, email, role, now_iso),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()

        return self._member_to_scim_user(row, tenant_id, base_url)

    def patch_user(
        self,
        tenant_id: str,
        user_id: str,
        base_url: str,
        patch_req: SCIMPatchRequest,
    ) -> SCIMUser:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise SCIMError(404, None, f"Tenant {tenant_id} not found")

        with self.tenant_store._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()
            if not row:
                raise SCIMError(404, None, f"User {user_id} not found")

            # Processa as operações de PATCH (RFC 7644)
            for op in patch_req.Operations:
                op_name = op.op.lower()
                path = (op.path or "").lower()
                val = op.value

                # Caso 1: Desativação do usuário (active: false)
                if path == "active" or (isinstance(val, dict) and "active" in val):
                    is_active = val if path == "active" else val["active"]
                    if str(is_active).lower() in {"false", "0"}:
                        # No SCIM, desativar um usuário pode removê-lo ou alterar o papel/status
                        # Se for o único owner, rejeita
                        if row["role"] == "owner":
                            owners_count = conn.execute(
                                "SELECT COUNT(*) as c FROM tenant_members WHERE tenant_id = ? AND role = 'owner'",
                                (tenant_id,),
                            ).fetchone()["c"]
                            if owners_count <= 1:
                                raise SCIMError(400, "mutability", "Cannot deactivate the sole owner")

                        # Remove ou altera role para viewer/desativado
                        conn.execute(
                            "DELETE FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                            (tenant_id, user_id),
                        )
                        conn.commit()
                        # Retorna representação inativa
                        return SCIMUser(
                            schemas=[CORE_USER_SCHEMA],
                            id=user_id,
                            userName=row["email"] or user_id,
                            active=False,
                            meta=SCIMMeta(
                                resourceType="User",
                                created=row["joined_at"],
                                lastModified=datetime.now(timezone.utc).isoformat(),
                                location=f"{base_url.rstrip('/')}/scim/v2/tenants/{tenant_id}/Users/{user_id}",
                            ),
                        )

                # Caso 2: Atualização de Papel (roles)
                if path == "roles" or (isinstance(val, dict) and "roles" in val):
                    new_role_list = val if path == "roles" else val["roles"]
                    new_role = None
                    if isinstance(new_role_list, list) and len(new_role_list) > 0:
                        first = new_role_list[0]
                        new_role = first.get("value") if isinstance(first, dict) else str(first)
                    elif isinstance(new_role_list, str):
                        new_role = new_role_list

                    if new_role in {"owner", "admin", "statistician", "analyst", "viewer"}:
                        conn.execute(
                            "UPDATE tenant_members SET role = ? WHERE tenant_id = ? AND user_id = ?",
                            (new_role, tenant_id, user_id),
                        )
                        conn.commit()

            # Recarrega usuário
            updated_row = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()

        if not updated_row:
            return SCIMUser(
                schemas=[CORE_USER_SCHEMA],
                id=user_id,
                userName=row["email"] or user_id,
                active=False,
                meta=SCIMMeta(
                    resourceType="User",
                    created=row["joined_at"],
                    lastModified=datetime.now(timezone.utc).isoformat(),
                    location=f"{base_url.rstrip('/')}/scim/v2/tenants/{tenant_id}/Users/{user_id}",
                ),
            )

        return self._member_to_scim_user(updated_row, tenant_id, base_url)

    def delete_user(self, tenant_id: str, user_id: str) -> None:
        tenant = self.tenant_store.get_tenant(tenant_id)
        if not tenant:
            raise SCIMError(404, None, f"Tenant {tenant_id} not found")

        try:
            removed = self.tenant_store.remove_member(tenant_id, user_id)
            if not removed:
                raise SCIMError(404, None, f"User {user_id} not found in tenant {tenant_id}")
        except ValueError as e:
            raise SCIMError(400, "mutability", str(e))
