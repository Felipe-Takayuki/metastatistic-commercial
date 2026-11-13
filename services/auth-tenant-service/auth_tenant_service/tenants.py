import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from auth_tenant_service.models import (
    InvitationCreate,
    InvitationResponse,
    RoleType,
    TenantCreate,
    TenantMemberResponse,
    TenantResponse,
    TierType,
    AcceptInvitationRequest,
)

TIER_QUOTAS: Dict[str, Dict[str, Any]] = {
    "community": {  # plano Free
        "max_users": 3,
        "max_datasets": 5,
        "max_upload_mb": 10,
        "max_storage_mb": 50,
        "features": ["jasp_engine", "csv_import", "sqlite_export"],
        "rate_limit_per_min": 60,
    },
    "team": {  # plano Pro
        "max_users": 15,
        "max_datasets": 100,
        "max_upload_mb": 200,
        "max_storage_mb": 10000,
        "features": ["jasp_engine", "csv_import", "postgres_connector", "team_sharing"],
        "rate_limit_per_min": 300,
    },
    "enterprise": {
        "max_users": 1_000_000,
        "max_datasets": 1_000_000,
        "max_upload_mb": 10_000,
        "max_storage_mb": 10_000_000,
        "features": ["jasp_engine", "proprietary_engine", "all_connectors", "sso_saml", "audit_log", "unlimited"],
        "rate_limit_per_min": 5000,
    },
}

PLAN_NAMES = {"community": "Free", "team": "Pro", "enterprise": "Enterprise"}


def users_quota_message(tier: str, limit: int) -> str:
    """Mensagem do limite de usuários: diz o limite do plano e como liberar mais."""
    name = PLAN_NAMES.get(tier, tier)
    if tier == "community":
        upgrade = f"Faça upgrade para o plano Pro (Planos > Assinar o Pro) para liberar até {TIER_QUOTAS['team']['max_users']} usuários."
    elif tier == "team":
        upgrade = "Para mais usuários, fale com a nossa equipe sobre o plano Enterprise."
    else:
        upgrade = "Remova um membro ou convite pendente para liberar uma vaga."
    return f"Limite do plano {name}: até {limit} usuários por organização. {upgrade}"


VALID_ROLES: set[RoleType] = {"owner", "admin", "statistician", "analyst", "viewer"}


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "tenant"


class QuotaExceededError(Exception):
    pass


class TenantNotFoundError(Exception):
    pass


class InvitationError(Exception):
    pass


class TenantStore:
    def __init__(self, db_path: str = "./auth_tenant.db"):
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "")
        elif db_path.startswith("sqlite://"):
            self.db_path = db_path.replace("sqlite://", "")
        else:
            self.db_path = db_path

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS tenant_members (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    email TEXT,
                    role TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, user_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
                );
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
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    details TEXT DEFAULT '{}',
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
                CREATE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);
                CREATE INDEX IF NOT EXISTS idx_tenant_members_user ON tenant_members(user_id);
                CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_log(tenant_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
            """)

    def create_tenant(self, data: TenantCreate) -> TenantResponse:
        base_slug = data.slug or slugify(data.name)
        slug = base_slug
        now_iso = datetime.now(timezone.utc).isoformat()
        tenant_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            # Garante unicidade do slug se já existir
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tenants WHERE slug = ?", (slug,))
            if cursor.fetchone():
                slug = f"{base_slug}-{secrets.token_hex(3)}"

            cursor.execute(
                """
                INSERT INTO tenants (id, name, slug, tier, status, created_at, metadata)
                VALUES (?, ?, ?, ?, 'active', ?, '{}')
                """,
                (tenant_id, data.name, slug, data.tier, now_iso),
            )
            # Insere o criador como 'owner'
            cursor.execute(
                """
                INSERT INTO tenant_members (tenant_id, user_id, email, role, joined_at)
                VALUES (?, ?, ?, 'owner', ?)
                """,
                (tenant_id, data.owner_id, data.owner_email, now_iso),
            )
            conn.commit()

        quotas = TIER_QUOTAS.get(data.tier, TIER_QUOTAS["community"])
        return TenantResponse(
            id=tenant_id,
            name=data.name,
            slug=slug,
            tier=data.tier,
            status="active",
            created_at=now_iso,
            quotas=quotas,
            members_count=1,
        )

    def stats_by_tier(self) -> Dict[str, Any]:
        """Organizações e usuários por tier, para o painel admin do billing (usuário em duas organizações conta em cada uma)."""
        with self._get_connection() as conn:
            tenants = {r["tier"]: r["n"] for r in conn.execute("SELECT tier, COUNT(*) AS n FROM tenants GROUP BY tier")}
            users = {
                r["tier"]: r["n"]
                for r in conn.execute(
                    "SELECT t.tier AS tier, COUNT(DISTINCT m.user_id) AS n FROM tenant_members m "
                    "JOIN tenants t ON t.id = m.tenant_id GROUP BY t.tier"
                )
            }
            total = conn.execute("SELECT COUNT(DISTINCT user_id) AS n FROM tenant_members").fetchone()["n"]
        return {"tenants_by_tier": tenants, "users_by_tier": users, "users_total": total}

    def get_tenant(self, tenant_id: str) -> Optional[TenantResponse]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
            if not row:
                return None
            m_count = conn.execute(
                "SELECT COUNT(*) as count FROM tenant_members WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()["count"]

        quotas = TIER_QUOTAS.get(row["tier"], TIER_QUOTAS["community"])
        return TenantResponse(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            tier=row["tier"],
            status=row["status"],
            created_at=row["created_at"],
            quotas=quotas,
            members_count=m_count,
        )

    def get_tenant_by_slug(self, slug: str) -> Optional[TenantResponse]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
            if not row:
                return None
            m_count = conn.execute(
                "SELECT COUNT(*) as count FROM tenant_members WHERE tenant_id = ?", (row["id"],)
            ).fetchone()["count"]

        quotas = TIER_QUOTAS.get(row["tier"], TIER_QUOTAS["community"])
        return TenantResponse(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            tier=row["tier"],
            status=row["status"],
            created_at=row["created_at"],
            quotas=quotas,
            members_count=m_count,
        )

    def update_tenant_tier(self, tenant_id: str, new_tier: TierType) -> TenantResponse:
        if new_tier not in TIER_QUOTAS:
            raise ValueError(f"Invalid tier: {new_tier}. Must be one of {list(TIER_QUOTAS.keys())}")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
            row = cursor.fetchone()
            if not row:
                raise TenantNotFoundError(f"Tenant {tenant_id} not found")
            cursor.execute("UPDATE tenants SET tier = ? WHERE id = ?", (new_tier, tenant_id))
            conn.commit()
            m_count = cursor.execute(
                "SELECT COUNT(*) as count FROM tenant_members WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()["count"]

        quotas = TIER_QUOTAS[new_tier]
        return TenantResponse(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            tier=new_tier,
            status=row["status"],
            created_at=row["created_at"],
            quotas=quotas,
            members_count=m_count,
        )

    def count_effective_users(self, tenant_id: str) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            members = conn.execute(
                "SELECT COUNT(*) as c FROM tenant_members WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()["c"]
            invitations = conn.execute(
                """
                SELECT COUNT(*) as c FROM invitations 
                WHERE tenant_id = ? AND accepted = 0 AND expires_at > ?
                """,
                (tenant_id, now_iso),
            ).fetchone()["c"]
        return members + invitations

    def create_invitation(self, tenant_id: str, data: InvitationCreate) -> InvitationResponse:
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        tier_quota = tenant.quotas.get("max_users", 3)
        current_users = self.count_effective_users(tenant_id)
        if current_users >= tier_quota:
            raise QuotaExceededError(users_quota_message(tenant.tier, tier_quota))

        inv_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_at = (now + timedelta(hours=data.expires_in_hours)).isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO invitations (id, tenant_id, email, role, token, created_at, expires_at, accepted)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (inv_id, tenant_id, data.email, data.role, token, now_iso, expires_at),
            )
            conn.commit()

        return InvitationResponse(
            id=inv_id,
            tenant_id=tenant_id,
            email=data.email,
            role=data.role,
            token=token,
            created_at=now_iso,
            expires_at=expires_at,
            accepted=False,
        )

    def accept_invitation(self, token: str, data: AcceptInvitationRequest) -> TenantMemberResponse:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM invitations WHERE token = ?", (token,))
            inv = cursor.fetchone()
            if not inv:
                raise InvitationError("Invitation not found")

            if inv["accepted"]:
                raise InvitationError("Invitation has already been accepted")

            if inv["expires_at"] < now_iso:
                raise InvitationError("Invitation has expired")

            tenant_id = inv["tenant_id"]
            role = inv["role"]
            email = data.email or inv["email"]

            # Checa se o usuário já é membro
            existing = cursor.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, data.user_id),
            ).fetchone()

            if existing:
                # Atualiza role
                cursor.execute(
                    "UPDATE tenant_members SET role = ?, email = ? WHERE tenant_id = ? AND user_id = ?",
                    (role, email, tenant_id, data.user_id),
                )
                joined_at = existing["joined_at"]
            else:
                # Checa quota
                tenant_row = cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
                if not tenant_row:
                    raise TenantNotFoundError(f"Tenant {tenant_id} not found")
                tier_quota = TIER_QUOTAS.get(tenant_row["tier"], TIER_QUOTAS["community"]).get("max_users", 3)
                current_members = cursor.execute(
                    "SELECT COUNT(*) as c FROM tenant_members WHERE tenant_id = ?", (tenant_id,)
                ).fetchone()["c"]
                if current_members >= tier_quota:
                    raise QuotaExceededError(users_quota_message(tenant_row["tier"], tier_quota))

                cursor.execute(
                    """
                    INSERT INTO tenant_members (tenant_id, user_id, email, role, joined_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (tenant_id, data.user_id, email, role, now_iso),
                )
                joined_at = now_iso

            # Marca convite como aceito
            cursor.execute("UPDATE invitations SET accepted = 1 WHERE id = ?", (inv["id"],))
            conn.commit()

        return TenantMemberResponse(
            user_id=data.user_id,
            email=email,
            role=role,
            joined_at=joined_at,
        )

    def list_members(self, tenant_id: str) -> List[TenantMemberResponse]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? ORDER BY joined_at ASC", (tenant_id,)
            ).fetchall()
            return [
                TenantMemberResponse(
                    user_id=r["user_id"],
                    email=r["email"],
                    role=r["role"],
                    joined_at=r["joined_at"],
                )
                for r in rows
            ]

    def get_member(self, tenant_id: str, user_id: str) -> Optional[TenantMemberResponse]:
        with self._get_connection() as conn:
            r = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()
            if not r:
                return None
            return TenantMemberResponse(
                user_id=r["user_id"],
                email=r["email"],
                role=r["role"],
                joined_at=r["joined_at"],
            )

    def update_member_role(self, tenant_id: str, user_id: str, role: RoleType) -> TenantMemberResponse:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")

        with self._get_connection() as conn:
            member = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?", (tenant_id, user_id)
            ).fetchone()
            if not member:
                raise TenantNotFoundError(f"Member {user_id} not found in tenant {tenant_id}")

            # Se estiver mudando de owner para outro papel, garanta que não seja o único owner
            if member["role"] == "owner" and role != "owner":
                owners_count = conn.execute(
                    "SELECT COUNT(*) as c FROM tenant_members WHERE tenant_id = ? AND role = 'owner'",
                    (tenant_id,),
                ).fetchone()["c"]
                if owners_count <= 1:
                    raise ValueError("Cannot remove role 'owner' from the sole owner of the tenant")

            conn.execute(
                "UPDATE tenant_members SET role = ? WHERE tenant_id = ? AND user_id = ?",
                (role, tenant_id, user_id),
            )
            conn.commit()

            return TenantMemberResponse(
                user_id=user_id,
                email=member["email"],
                role=role,
                joined_at=member["joined_at"],
            )

    def remove_member(self, tenant_id: str, user_id: str) -> bool:
        with self._get_connection() as conn:
            member = conn.execute(
                "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?", (tenant_id, user_id)
            ).fetchone()
            if not member:
                return False

            if member["role"] == "owner":
                owners_count = conn.execute(
                    "SELECT COUNT(*) as c FROM tenant_members WHERE tenant_id = ? AND role = 'owner'",
                    (tenant_id,),
                ).fetchone()["c"]
                if owners_count <= 1:
                    raise ValueError("Cannot remove the sole owner of the tenant")

            conn.execute(
                "DELETE FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            )
            conn.commit()
            return True
