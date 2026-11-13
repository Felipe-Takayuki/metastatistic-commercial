import pytest
from httpx import ASGITransport, AsyncClient

from auth_tenant_service.config import settings
from auth_tenant_service.jwt_auth import create_access_token, decode_access_token, InvalidTokenError, TokenExpiredError
from auth_tenant_service.main import app, get_store
from auth_tenant_service.tenants import TenantStore


@pytest.fixture
def memory_store(tmp_path):
    # Usa banco SQLite isolado para testes
    db_file = tmp_path / "test_auth.db"
    test_store = TenantStore(str(db_file))
    app.dependency_overrides[get_store] = lambda: test_store
    yield test_store
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_check(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "auth-tenant-service"


@pytest.mark.asyncio
async def test_auth_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_enabled"] is False
        assert data["needs_setup"] is False
        assert data["user"]["role"] == "admin"
        assert data["user"]["username"] == "anonymous"


@pytest.mark.asyncio
async def test_create_and_get_tenant(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria tenant
        payload = {
            "name": "BioTech Pharma",
            "tier": "team",
            "owner_id": "user_owner_1",
            "owner_email": "owner@biotech.com",
        }
        res = await client.post("/tenants", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "BioTech Pharma"
        assert data["slug"] == "biotech-pharma"
        assert data["tier"] == "team"
        assert data["quotas"]["max_users"] == 15
        tenant_id = data["id"]

        # Busca por ID
        res_get = await client.get(f"/tenants/{tenant_id}")
        assert res_get.status_code == 200
        assert res_get.json()["id"] == tenant_id

        # Busca por slug
        res_slug = await client.get("/tenants/by-slug/biotech-pharma")
        assert res_slug.status_code == 200
        assert res_slug.json()["id"] == tenant_id

        # Membros iniciais (deve conter o owner)
        res_members = await client.get(f"/tenants/{tenant_id}/members")
        assert res_members.status_code == 200
        members = res_members.json()
        assert len(members) == 1
        assert members[0]["user_id"] == "user_owner_1"
        assert members[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_jwt_auth_flow(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria tenant
        create_res = await client.post(
            "/tenants",
            json={"name": "Alpha Analytics", "tier": "enterprise", "owner_id": "alpha_boss"},
        )
        tenant = create_res.json()
        tenant_id = tenant["id"]

        # Emite token
        token_res = await client.post(
            "/auth/token",
            json={"user_id": "alpha_boss", "tenant_id": tenant_id},
        )
        assert token_res.status_code == 200
        token_data = token_res.json()
        access_token = token_data["access_token"]
        assert token_data["role"] == "owner"
        assert token_data["tier"] == "enterprise"

        # Valida token com /auth/verify
        verify_res = await client.post(
            "/auth/verify",
            json={"token": access_token},
        )
        assert verify_res.status_code == 200
        payload = verify_res.json()
        assert payload["sub"] == "alpha_boss"
        assert payload["tenant_id"] == tenant_id
        assert payload["role"] == "owner"
        assert payload["tier"] == "enterprise"


def test_jwt_unit_token_expired_and_invalid():
    # Token expirado
    token_exp = create_access_token(
        user_id="user1",
        tenant_id="t1",
        role="viewer",
        tier="community",
        secret_key="secret",
        expires_in_minutes=-10,  # no passado
    )
    with pytest.raises(TokenExpiredError):
        decode_access_token(token_exp, "secret")

    # Assinatura inválida
    token_valid = create_access_token(
        user_id="user1",
        tenant_id="t1",
        role="viewer",
        tier="community",
        secret_key="secret-correct",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token_valid, "secret-WRONG")


@pytest.mark.asyncio
async def test_invitations_and_tier_quota_enforcement(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria tenant com tier Community (max 3 usuários)
        res = await client.post(
            "/tenants",
            json={"name": "Small Lab", "tier": "community", "owner_id": "owner_1"},
        )
        tenant_id = res.json()["id"]

        # Convite 1 (segundo usuário potencial)
        inv1 = await client.post(
            f"/tenants/{tenant_id}/invitations",
            json={"email": "user2@lab.com", "role": "statistician"},
        )
        assert inv1.status_code == 201
        token1 = inv1.json()["token"]

        # Aceita convite 1
        acc1 = await client.post(
            f"/tenants/invitations/{token1}/accept",
            json={"user_id": "user_2", "email": "user2@lab.com"},
        )
        assert acc1.status_code == 200
        assert acc1.json()["role"] == "statistician"

        # Convite 2 (terceiro usuário potencial - limite da cota)
        inv2 = await client.post(
            f"/tenants/{tenant_id}/invitations",
            json={"email": "user3@lab.com", "role": "analyst"},
        )
        assert inv2.status_code == 201

        # Tentativa de convite 3 (quarto usuário) -> DEVE FALHAR COM 403 QUOTA EXCEEDED
        inv3 = await client.post(
            f"/tenants/{tenant_id}/invitations",
            json={"email": "user4@lab.com", "role": "viewer"},
        )
        assert inv3.status_code == 403
        detail = inv3.json()["detail"]
        # a mensagem diz o limite do plano e como liberar mais
        assert "plano Free" in detail and "3 usuários" in detail and "plano Pro" in detail


@pytest.mark.asyncio
async def test_member_management_and_sole_owner_protection(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/tenants",
            json={"name": "Clinical Data Corp", "tier": "team", "owner_id": "boss_dr"},
        )
        tenant_id = res.json()["id"]

        # Tentar remover o único owner deve falhar com 400
        del_res = await client.delete(f"/tenants/{tenant_id}/members/boss_dr")
        assert del_res.status_code == 400
        assert "sole owner" in del_res.json()["detail"].lower()

        # Tentar alterar role do único owner para viewer deve falhar com 400
        patch_res = await client.patch(
            f"/tenants/{tenant_id}/members/boss_dr",
            json={"role": "viewer"},
        )
        assert patch_res.status_code == 400

        # Adiciona segundo membro via convite
        inv = await client.post(
            f"/tenants/{tenant_id}/invitations",
            json={"email": "colleague@corp.com", "role": "analyst"},
        )
        token = inv.json()["token"]
        await client.post(
            f"/tenants/invitations/{token}/accept",
            json={"user_id": "colleague_1", "email": "colleague@corp.com"},
        )

        # Promove colega para statistician
        update_res = await client.patch(
            f"/tenants/{tenant_id}/members/colleague_1",
            json={"role": "statistician"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["role"] == "statistician"

        # Remove colega
        del_colleague = await client.delete(f"/tenants/{tenant_id}/members/colleague_1")
        assert del_colleague.status_code == 204


@pytest.mark.asyncio
async def test_update_tenant_tier(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cria tenant community
        payload = {
            "name": "Acme Analytics",
            "tier": "community",
            "owner_id": "user_acme_1",
            "owner_email": "owner@acme.com",
        }
        res = await client.post("/tenants", json=payload)
        assert res.status_code == 201
        tenant_id = res.json()["id"]
        assert res.json()["tier"] == "community"
        assert res.json()["quotas"]["max_users"] == 3

        # Upgrade para enterprise
        patch_res = await client.patch(f"/tenants/{tenant_id}/tier", json={"tier": "enterprise"})
        assert patch_res.status_code == 200
        upgraded = patch_res.json()
        assert upgraded["tier"] == "enterprise"
        assert upgraded["quotas"]["max_users"] == 1_000_000
        assert "sso_saml" in upgraded["quotas"]["features"]

        # Downgrade para team
        patch_res2 = await client.patch(f"/tenants/{tenant_id}/tier", json={"tier": "team"})
        assert patch_res2.status_code == 200
        downgraded = patch_res2.json()
        assert downgraded["tier"] == "team"
        assert downgraded["quotas"]["max_users"] == 15

        # Tier inexistente dá 422 (validação Pydantic)
        bad_tier = await client.patch(f"/tenants/{tenant_id}/tier", json={"tier": "invalid_tier"})
        assert bad_tier.status_code == 422

        # Tenant inexistente dá 404
        not_found = await client.patch("/tenants/non-existent-tenant-id/tier", json={"tier": "team"})
        assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_tenant_access_endpoint(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/tenants", json={
            "name": "Access Lab", "tier": "team", "owner_id": "u_owner", "owner_email": "o@a.io",
        })).json()

        by_id = await client.get(f"/tenants/{created['id']}/access/u_owner")
        assert by_id.status_code == 200
        assert by_id.json() == {"tenant_id": created["id"], "tenant_slug": created["slug"], "tier": "team", "role": "owner"}

        by_slug = await client.get(f"/tenants/{created['slug']}/access/u_owner")
        assert by_slug.status_code == 200 and by_slug.json()["tenant_id"] == created["id"]

        # não-membro e tenant inexistente são indistinguíveis (404)
        assert (await client.get(f"/tenants/{created['id']}/access/u_stranger")).status_code == 404
        assert (await client.get("/tenants/nao-existe/access/u_owner")).status_code == 404


@pytest.mark.asyncio
async def test_plan_stats_for_admin_panel(memory_store):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/tenants", json={"name": "Lab Free", "tier": "community", "owner_id": "u1"})
        pro = await client.post("/tenants", json={"name": "Lab Pro", "tier": "team", "owner_id": "u2"})
        inv = await client.post(f"/tenants/{pro.json()['id']}/invitations", json={"email": "c@lab.com", "role": "analyst"})
        await client.post(f"/tenants/invitations/{inv.json()['token']}/accept", json={"user_id": "u3", "email": "c@lab.com"})

        stats = (await client.get("/tenants/stats/plans")).json()
        assert stats["tenants_by_tier"] == {"community": 1, "team": 1}
        assert stats["users_by_tier"] == {"community": 1, "team": 2}
        assert stats["users_total"] == 3
