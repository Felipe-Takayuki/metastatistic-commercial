import pytest
from fastapi.testclient import TestClient

from bi_report_service.config import settings
from bi_report_service.db import init_db
from bi_report_service.main import app


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_bi.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{test_db}")
    init_db()


def test_health_check():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "bi-report-service"


def test_reports_crud_and_optimistic_locking():
    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant_test"}

    # 1. Create Report
    create_payload = {
        "title": "Clinical Efficacy Study",
        "blocks": [
            {
                "id": "b1",
                "type": "heading",
                "content": "Executive Summary",
                "order": 1,
            },
            {
                "id": "b2",
                "type": "text",
                "content": "Primary endpoint achieved statistical significance.",
                "order": 2,
            },
            {
                "id": "b3",
                "type": "table_apa",
                "content": {
                    "caption": "Table 1. Descriptive Statistics by Cohort",
                    "headers": ["Cohort", "N", "Mean (SD)", "p-value"],
                    "rows": [["Control", "50", "4.21 (1.10)", "-"], ["Treatment", "52", "6.85 (0.95)", "< .001"]],
                },
                "order": 3,
            },
        ],
    }
    resp = client.post("/reports", json=create_payload, headers=headers)
    assert resp.status_code == 201
    report = resp.json()
    assert report["id"] is not None
    assert report["version"] == 1
    assert report["tenant_id"] == "tenant_test"
    assert len(report["blocks"]) == 3
    report_id = report["id"]

    # 2. Get Report
    resp_get = client.get(f"/reports/{report_id}", headers=headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["title"] == "Clinical Efficacy Study"

    # 3. Successful Update with version 1
    update_payload = {
        "title": "Clinical Efficacy Study - Final",
        "blocks": report["blocks"],
        "version": 1,
    }
    resp_up = client.put(f"/reports/{report_id}", json=update_payload, headers=headers)
    assert resp_up.status_code == 200
    updated = resp_up.json()
    assert updated["title"] == "Clinical Efficacy Study - Final"
    assert updated["version"] == 2

    # 4. Conflicting Update: Client tries to update using outdated version 1
    resp_conflict = client.put(f"/reports/{report_id}", json=update_payload, headers=headers)
    assert resp_conflict.status_code == 409
    assert "Conflict" in resp_conflict.json()["detail"]

    # 5. Delete Report
    resp_del = client.delete(f"/reports/{report_id}", headers=headers)
    assert resp_del.status_code == 204

    # 6. Not Found after deletion
    resp_gone = client.get(f"/reports/{report_id}", headers=headers)
    assert resp_gone.status_code == 404


def test_snapshots_create_and_restore():
    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant_snap"}

    # Criar relatório inicial
    create_payload = {
        "title": "Version 1 Title",
        "blocks": [{"id": "b1", "type": "text", "content": "Initial text", "order": 1}],
    }
    rep1 = client.post("/reports", json=create_payload, headers=headers).json()
    rep_id = rep1["id"]

    # Criar snapshot da versão 1
    snap_resp = client.post(
        f"/reports/{rep_id}/snapshots",
        json={"note": "Pre-revision baseline"},
        headers=headers,
    )
    assert snap_resp.status_code == 201
    snap = snap_resp.json()
    assert snap["version"] == 1
    assert snap["title"] == "Version 1 Title"
    assert snap["note"] == "Pre-revision baseline"
    snap_id = snap["id"]

    # Listar snapshots
    snaps_list = client.get(f"/reports/{rep_id}/snapshots", headers=headers).json()
    assert len(snaps_list) == 1
    assert snaps_list[0]["id"] == snap_id

    # Atualizar relatório para versão 2
    client.put(
        f"/reports/{rep_id}",
        json={
            "title": "Version 2 Corrupted Title",
            "blocks": [{"id": "b1", "type": "text", "content": "Modified text", "order": 1}],
            "version": 1,
        },
        headers=headers,
    )
    rep2 = client.get(f"/reports/{rep_id}", headers=headers).json()
    assert rep2["version"] == 2
    assert rep2["title"] == "Version 2 Corrupted Title"

    # Restaurar a partir do snapshot
    restored = client.post(
        f"/reports/{rep_id}/snapshots/{snap_id}/restore",
        headers=headers,
    ).json()
    assert restored["title"] == "Version 1 Title"
    assert restored["version"] == 3  # Incrementa a versão atual
    assert restored["blocks"][0]["content"] == "Initial text"


def test_dashboards_crud_and_optimistic_locking():
    client = TestClient(app)
    headers = {"X-Tenant-ID": "tenant_dash"}

    dash_payload = {
        "title": "Cohort Overview Dashboard",
        "tiles": [
            {
                "id": "t1",
                "type": "kpi",
                "title": "Total Subjects",
                "x": 0,
                "y": 0,
                "w": 3,
                "h": 2,
                "config": {"value": 102, "trend": "+12%"},
            },
            {
                "id": "t2",
                "type": "chart",
                "title": "Efficacy Trend",
                "x": 3,
                "y": 0,
                "w": 9,
                "h": 6,
                "config": {"chart_type": "line", "x": "day", "ys": ["score"]},
            },
        ],
        "filters": [{"column": "site_id", "operator": "eq", "value": "NYC"}],
    }
    resp = client.post("/dashboards", json=dash_payload, headers=headers)
    assert resp.status_code == 201
    dash = resp.json()
    dash_id = dash["id"]
    assert dash["version"] == 1
    assert len(dash["tiles"]) == 2

    # Update sucesso
    up_payload = {
        "title": "Cohort Overview Dashboard - Revised",
        "tiles": dash["tiles"],
        "filters": dash["filters"],
        "version": 1,
    }
    up_resp = client.put(f"/dashboards/{dash_id}", json=up_payload, headers=headers)
    assert up_resp.status_code == 200
    assert up_resp.json()["version"] == 2

    # Conflito 409 ao reutilizar versão 1
    conf_resp = client.put(f"/dashboards/{dash_id}", json=up_payload, headers=headers)
    assert conf_resp.status_code == 409

    # Delete
    del_resp = client.delete(f"/dashboards/{dash_id}", headers=headers)
    assert del_resp.status_code == 204


def test_multi_tenant_isolation():
    client = TestClient(app)
    h_tenant_a = {"X-Tenant-ID": "tenant_alpha"}
    h_tenant_b = {"X-Tenant-ID": "tenant_beta"}

    # Cria report no Tenant A
    rep_a = client.post(
        "/reports",
        json={"title": "Confidential Alpha Report", "blocks": []},
        headers=h_tenant_a,
    ).json()

    # Cria dashboard no Tenant A
    dash_a = client.post(
        "/dashboards",
        json={"title": "Confidential Alpha Dashboard", "tiles": []},
        headers=h_tenant_a,
    ).json()

    # Tenant B NÃO deve ver os itens de Tenant A
    list_rep_b = client.get("/reports", headers=h_tenant_b).json()
    assert all(r["id"] != rep_a["id"] for r in list_rep_b)

    list_dash_b = client.get("/dashboards", headers=h_tenant_b).json()
    assert all(d["id"] != dash_a["id"] for d in list_dash_b)

    # Tenant B tentando acessar ID direto do Tenant A -> 404
    get_rep_b = client.get(f"/reports/{rep_a['id']}", headers=h_tenant_b)
    assert get_rep_b.status_code == 404

    get_dash_b = client.get(f"/dashboards/{dash_a['id']}", headers=h_tenant_b)
    assert get_dash_b.status_code == 404


def test_websocket_collaboration():
    client = TestClient(app)
    report_id = "ws_test_rep_101"

    with client.websocket_connect(f"/ws/reports/{report_id}?user_id=analyst_1") as ws1:
        join_msg = ws1.receive_json()
        assert join_msg["event"] == "USER_JOINED"
        assert join_msg["user_id"] == "analyst_1"

        with client.websocket_connect(f"/ws/reports/{report_id}?user_id=analyst_2") as ws2:
            # ws1 deve receber notificação de entrada de analyst_2
            peer_joined = ws1.receive_json()
            assert peer_joined["event"] == "USER_JOINED"
            assert peer_joined["user_id"] == "analyst_2"

            # analyst_2 envia alteração de bloco
            ws2.send_json({"type": "BLOCK_UPDATED", "block_id": "b1", "text": "Novo parágrafo"})
            update_received = ws1.receive_json()
            assert update_received["type"] == "BLOCK_UPDATED"
            assert update_received["from_user"] == "analyst_2"
