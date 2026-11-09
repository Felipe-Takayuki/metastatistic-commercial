import base64
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_store
from app.tenants import TenantStore


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "enterprise_test.db"
    test_store = TenantStore(str(db_file))
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def enterprise_tenant(client):
    resp = client.post(
        "/tenants",
        json={
            "name": "Acme Enterprise Corp",
            "slug": "acme-corp",
            "tier": "enterprise",
            "owner_id": "owner_123",
            "owner_email": "owner@acme.corp",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_sso_saml_configuration_and_login_flow(client, enterprise_tenant):
    tenant_id = enterprise_tenant["id"]

    # 1. Configurar SSO SAML
    config_payload = {
        "provider_type": "saml",
        "enabled": True,
        "idp_entity_id": "https://idp.okta.com/acme",
        "idp_sso_url": "https://acme.okta.com/app/sso/saml",
        "sp_entity_id": "https://metastatistic.acme.com/saml/metadata",
        "jit_provisioning": True,
        "default_role": "statistician",
    }
    resp = client.post(f"/tenants/{tenant_id}/sso/config", json=config_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_type"] == "saml"
    assert data["default_role"] == "statistician"

    # 2. Obter configuração
    resp = client.get(f"/tenants/{tenant_id}/sso/config")
    assert resp.status_code == 200
    assert resp.json()["idp_entity_id"] == "https://idp.okta.com/acme"

    # 3. Iniciar login SSO
    resp = client.post(
        "/auth/sso/login",
        json={"tenant_id": tenant_id, "redirect_url": f"tenant:{tenant_id}/dashboard"},
    )
    assert resp.status_code == 200
    login_info = resp.json()
    assert login_info["provider_type"] == "saml"
    assert "SAMLRequest" in login_info["auth_url"]
    assert login_info["saml_request"] is not None

    # 4. SAML ACS com Provisionamento JIT (Just-In-Time)
    saml_response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                    ID="RESP_{uuid.uuid4().hex}" Version="2.0">
        <samlp:Status>
            <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
        </samlp:Status>
        <saml:Assertion ID="ASSERT_{uuid.uuid4().hex}" Version="2.0">
            <saml:Subject>
                <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">
                    lead_analyst@acme.corp
                </saml:NameID>
            </saml:Subject>
            <saml:AttributeStatement>
                <saml:Attribute Name="displayName">
                    <saml:AttributeValue>Jane Lead Statistician</saml:AttributeValue>
                </saml:Attribute>
                <saml:Attribute Name="email">
                    <saml:AttributeValue>lead_analyst@acme.corp</saml:AttributeValue>
                </saml:Attribute>
                <saml:Attribute Name="role">
                    <saml:AttributeValue>statistician</saml:AttributeValue>
                </saml:Attribute>
            </saml:AttributeStatement>
        </saml:Assertion>
    </samlp:Response>"""

    saml_b64 = base64.b64encode(saml_response_xml.encode("utf-8")).decode("ascii")

    acs_resp = client.post(
        "/auth/sso/saml/acs",
        json={
            "SAMLResponse": saml_b64,
            "tenant_id": tenant_id,
            "RelayState": f"tenant:{tenant_id}/dashboard",
        },
    )
    assert acs_resp.status_code == 200
    token_data = acs_resp.json()
    assert "access_token" in token_data
    assert token_data["tenant_id"] == tenant_id
    assert token_data["role"] == "statistician"
    assert token_data["tier"] == "enterprise"

    # 5. Verifica se o usuário foi provisionado como membro do tenant
    members_resp = client.get(f"/tenants/{tenant_id}/members")
    assert members_resp.status_code == 200
    members = members_resp.json()
    emails = [m["email"] for m in members]
    assert "lead_analyst@acme.corp" in emails

    # 6. Valida o JWT emitido
    verify_resp = client.post("/auth/verify", json={"token": token_data["access_token"]})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["email"] == "lead_analyst@acme.corp"


def test_sso_oidc_flow(client, enterprise_tenant):
    tenant_id = enterprise_tenant["id"]

    # 1. Configura OIDC
    config_payload = {
        "provider_type": "oidc",
        "enabled": True,
        "oidc_issuer": "https://accounts.google.com",
        "oidc_client_id": "google-client-12345",
        "oidc_auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "default_role": "analyst",
    }
    client.post(f"/tenants/{tenant_id}/sso/config", json=config_payload)

    # 2. Inicia login OIDC
    resp = client.post("/auth/sso/login", json={"tenant_id": tenant_id})
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["provider_type"] == "oidc"
    assert "google-client-12345" in res_json["auth_url"]

    # 3. Callback OIDC com JIT provisioning
    callback_resp = client.post(
        "/auth/sso/oidc/callback",
        json={
            "code": "authcode:scientist@acme.corp",
            "tenant_id": tenant_id,
            "state": res_json["state"],
        },
    )
    assert callback_resp.status_code == 200
    token_data = callback_resp.json()
    assert token_data["role"] == "analyst"
    assert token_data["tenant_id"] == tenant_id

    # Verifica membro
    members_resp = client.get(f"/tenants/{tenant_id}/members")
    emails = [m["email"] for m in members_resp.json()]
    assert "scientist@acme.corp" in emails


def test_scim_service_provider_config_and_schemas(client, enterprise_tenant):
    tenant_id = enterprise_tenant["id"]

    # ServiceProviderConfig
    resp = client.get(f"/scim/v2/tenants/{tenant_id}/ServiceProviderConfig")
    assert resp.status_code == 200
    assert "application/scim+json" in resp.headers["content-type"]
    data = resp.json()
    assert "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig" in data["schemas"]
    assert data["patch"]["supported"] is True

    # Schemas
    resp = client.get(f"/scim/v2/tenants/{tenant_id}/Schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["Resources"]) > 0
    assert data["Resources"][0]["id"] == "urn:ietf:params:scim:schemas:core:2.0:User"


def test_scim_user_crud_and_deactivation(client, enterprise_tenant):
    tenant_id = enterprise_tenant["id"]

    # 1. Criar Usuário via SCIM POST
    scim_user_payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": "dr.smith@acme.corp",
        "displayName": "Dr. Smith",
        "emails": [{"value": "dr.smith@acme.corp", "primary": True}],
        "roles": [{"value": "statistician"}],
        "active": True,
    }

    create_resp = client.post(
        f"/scim/v2/tenants/{tenant_id}/Users",
        json=scim_user_payload,
    )
    assert create_resp.status_code == 201
    assert "application/scim+json" in create_resp.headers["content-type"]
    user_data = create_resp.json()
    user_id = user_data["id"]
    assert user_data["userName"] == "dr.smith@acme.corp"
    assert user_data["active"] is True
    assert "Location" in create_resp.headers

    # 2. Obter usuário via SCIM GET
    get_resp = client.get(f"/scim/v2/tenants/{tenant_id}/Users/{user_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == user_id

    # 3. Filtrar usuários por userName
    filter_resp = client.get(
        f'/scim/v2/tenants/{tenant_id}/Users?filter=userName eq "dr.smith@acme.corp"'
    )
    assert filter_resp.status_code == 200
    list_data = filter_resp.json()
    assert list_data["totalResults"] == 1
    assert list_data["Resources"][0]["id"] == user_id

    # 4. Desativar Usuário via SCIM PATCH (active: false)
    patch_payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {
                "op": "replace",
                "path": "active",
                "value": False,
            }
        ],
    }
    patch_resp = client.patch(
        f"/scim/v2/tenants/{tenant_id}/Users/{user_id}",
        json=patch_payload,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["active"] is False

    # 5. Criar outro usuário e deletar via SCIM DELETE
    user2_resp = client.post(
        f"/scim/v2/tenants/{tenant_id}/Users",
        json={"userName": "temp_user@acme.corp"},
    )
    assert user2_resp.status_code == 201
    user2_id = user2_resp.json()["id"]

    del_resp = client.delete(f"/scim/v2/tenants/{tenant_id}/Users/{user2_id}")
    assert del_resp.status_code == 204

    # Confirma que foi removido
    get_del = client.get(f"/scim/v2/tenants/{tenant_id}/Users/{user2_id}")
    assert get_del.status_code == 404


def test_immutable_audit_trail_and_tamper_detection(client, enterprise_tenant):
    tenant_id = enterprise_tenant["id"]

    # 1. Registrar cadeia de eventos de auditoria
    actions = [
        ("auth.login", "session", {"ip": "192.168.1.10"}),
        ("dataset.upload", "dataset", {"filename": "clinical_trial_phase3.csv", "records": 50000}),
        ("analysis.anova", "job", {"model": "two-way-anova", "p_value": 0.0012}),
        ("report.export", "report", {"format": "pdf_fda_compliant"}),
    ]

    recorded_events = []
    for action, res_type, details in actions:
        ev_resp = client.post(
            "/audit/events",
            json={
                "tenant_id": tenant_id,
                "user_id": "investigator_01",
                "action": action,
                "resource_type": res_type,
                "details": details,
                "ip_address": "10.0.0.1",
            },
        )
        assert ev_resp.status_code == 201
        recorded_events.append(ev_resp.json())

    # 2. Verificar encadeamento SHA-256 e integridade matemática
    verify_resp = client.get(f"/audit/verify?tenant_id={tenant_id}")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["total_records"] >= 4
    assert v_data["latest_hash"] is not None
    assert v_data["tampered_at_id"] is None

    # 3. Exportar relatório de auditoria SOC 2 / FDA 21 CFR Part 11
    export_resp = client.get(f"/audit/export?tenant_id={tenant_id}")
    assert export_resp.status_code == 200
    exp_data = export_resp.json()
    assert exp_data["compliance_standard"] == "SOC 2 Type II / FDA 21 CFR Part 11"
    assert exp_data["integrity_verified"] is True
    assert len(exp_data["events"]) >= 4

    # 4. TESTE DE ADULTERAÇÃO INTENCIONAL (Direct DB Tampering)
    # Simulamos um atacante com acesso SQL direto alterando o conteúdo de um log histórico
    store = client.app.dependency_overrides[get_store]()
    target_event = recorded_events[1]  # dataset.upload
    tampered_id = target_event["id"]

    with store._get_connection() as conn:
        conn.execute(
            "UPDATE audit_log SET details = ? WHERE id = ?",
            ('{"filename": "clinical_trial_phase3.csv", "records": 99999999, "tampered": true}', tampered_id),
        )
        conn.commit()

    # 5. Executa novamente a verificação matemática
    tamper_verify = client.get(f"/audit/verify?tenant_id={tenant_id}")
    assert tamper_verify.status_code == 200
    t_data = tamper_verify.json()

    # Comprova matematicamente a detecção da fraude e aponta o registro corrompido!
    assert t_data["valid"] is False
    assert t_data["tampered_at_id"] == tampered_id
    assert t_data["tampered_event_id"] == target_event["event_id"]
    assert "Content tampering detected" in t_data["reason"]
