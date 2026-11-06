import pytest
from conftest import SALES_CSV
from test_auth import auth_on, login, make_user, new_client, setup_admin  # noqa: F401


@pytest.fixture
async def team(client, auth_on):
    """Admin (o `client`), dois editores e um leitor, cada um com seu cliente HTTP."""
    await setup_admin(client)
    for name, role in [("ed1", "editor"), ("ed2", "editor"), ("leitor", "viewer")]:
        await make_user(client, name, role)
    return {"admin": client, "ed1": await login("ed1"), "ed2": await login("ed2"), "leitor": await login("leitor")}


async def new_report(c, title="R"):
    r = await c.post("/reports", json={"title": title, "blocks": []})
    assert r.status_code == 201, r.text
    return r.json()


async def test_creator_is_recorded_and_annotated(team):
    rep = await new_report(team["ed1"])
    assert rep["owner_name"] == "ed1" and rep["can_edit"] is True and rep["collection_id"] is None
    as_ed2 = (await team["ed2"].get(f"/reports/{rep['id']}")).json()
    assert as_ed2["owner_name"] == "ed1" and as_ed2["can_edit"] is False
    assert (await team["admin"].get(f"/reports/{rep['id']}")).json()["can_edit"] is True
    assert (await team["leitor"].get(f"/reports/{rep['id']}")).json()["can_edit"] is False
    listed = (await team["ed2"].get("/reports")).json()
    assert listed[0]["owner_name"] == "ed1" and listed[0]["can_edit"] is False


async def test_only_owner_or_admin_changes_report(team):
    rep = await new_report(team["ed1"])
    body = {"title": "novo", "blocks": [], "version": rep["version"]}
    assert (await team["ed2"].put(f"/reports/{rep['id']}", json=body)).status_code == 403
    assert (await team["ed2"].delete(f"/reports/{rep['id']}")).status_code == 403
    assert (await team["ed2"].put(f"/reports/{rep['id']}/collection", json={"collection_id": None})).status_code == 403
    ok = await team["ed1"].put(f"/reports/{rep['id']}", json=body)
    assert ok.status_code == 200 and ok.json()["title"] == "novo" and ok.json()["owner_name"] == "ed1"
    body["version"] = ok.json()["version"]
    assert (await team["admin"].put(f"/reports/{rep['id']}", json=body)).status_code == 200  # admin altera qualquer um
    assert (await team["ed1"].delete(f"/reports/{rep['id']}")).status_code == 204


async def test_only_owner_or_admin_changes_dashboard_and_dataset(team):
    d = (await team["ed1"].post("/dashboards", json={"title": "D", "tiles": []})).json()
    assert (await team["ed2"].delete(f"/dashboards/{d['id']}")).status_code == 403
    ds = (await team["ed1"].post("/datasets", files={"file": ("v.csv", SALES_CSV.encode(), "text/csv")})).json()
    assert ds["owner_name"] == "ed1"
    assert (await team["ed2"].patch(f"/datasets/{ds['id']}", json={"measurement": {"nota": "nominal"}})).status_code == 403
    assert (await team["ed2"].delete(f"/datasets/{ds['id']}")).status_code == 403
    assert (await team["ed2"].get(f"/datasets/{ds['id']}")).json()["can_edit"] is False  # mas ele lê e consulta
    assert (await team["ed1"].patch(f"/datasets/{ds['id']}", json={"measurement": {"nota": "nominal"}})).status_code == 200
    assert (await team["admin"].delete(f"/datasets/{ds['id']}")).status_code == 204
    assert (await team["ed1"].delete(f"/dashboards/{d['id']}")).status_code == 204


async def test_collections_crud_and_permissions(team):
    assert (await team["leitor"].post("/collections", json={"name": "x"})).status_code == 403
    c = (await team["ed1"].post("/collections", json={"name": "  Vendas  "})).json()
    assert c["name"] == "Vendas" and c["owner_name"] == "ed1" and c["can_edit"] is True and c["n_reports"] == 0
    assert (await team["ed1"].post("/collections", json={"name": "   "})).status_code == 422
    listed = (await team["ed2"].get("/collections")).json()
    assert [x["name"] for x in listed] == ["Vendas"] and listed[0]["can_edit"] is False
    assert (await team["leitor"].get("/collections")).status_code == 200
    assert (await team["ed2"].patch(f"/collections/{c['id']}", json={"name": "Outro"})).status_code == 403
    assert (await team["ed2"].delete(f"/collections/{c['id']}")).status_code == 403
    renamed = await team["ed1"].patch(f"/collections/{c['id']}", json={"name": "Financeiro"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Financeiro"
    assert (await team["ed1"].patch("/collections/inexistente", json={"name": "x"})).status_code == 404
    assert (await team["admin"].delete(f"/collections/{c['id']}")).status_code == 204


async def test_move_between_collections_and_delete_returns_items_to_root(team):
    rep, dash = await new_report(team["ed1"]), (await team["ed1"].post("/dashboards", json={"title": "D", "tiles": []})).json()
    c = (await team["ed1"].post("/collections", json={"name": "Q4"})).json()
    assert (await team["ed1"].put(f"/reports/{rep['id']}/collection", json={"collection_id": c["id"]})).status_code == 204
    assert (await team["ed1"].put(f"/dashboards/{dash['id']}/collection", json={"collection_id": c["id"]})).status_code == 204
    assert (await team["ed2"].get(f"/reports/{rep['id']}")).json()["collection_id"] == c["id"]
    assert (await team["ed2"].get("/dashboards")).json()[0]["collection_id"] == c["id"]
    col = (await team["ed2"].get("/collections")).json()[0]
    assert (col["n_reports"], col["n_dashboards"]) == (1, 1)
    # mover não mexe na versão (não conflita com quem edita)
    assert (await team["ed1"].get(f"/reports/{rep['id']}")).json()["version"] == rep["version"]
    bad = await team["ed1"].put(f"/reports/{rep['id']}/collection", json={"collection_id": "nao-existe"})
    assert bad.status_code == 404
    assert (await team["ed1"].delete(f"/collections/{c['id']}")).status_code == 204
    assert (await team["ed1"].get(f"/reports/{rep['id']}")).json()["collection_id"] is None  # voltou à raiz, não foi excluído
    assert (await team["ed1"].put(f"/reports/{rep['id']}/collection", json={"collection_id": None})).status_code == 204


async def test_deleted_report_leaves_no_ownership_row(team):
    rep = await new_report(team["ed1"])
    await team["ed1"].delete(f"/reports/{rep['id']}")
    import sqlite3
    from app.config import settings
    assert sqlite3.connect(settings.data_dir / "meta.db").execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0


async def test_deleting_a_user_orphans_their_items_to_everyone_editing(team):
    rep = await new_report(team["ed1"])
    users = {u["username"]: u["id"] for u in (await team["admin"].get("/users")).json()}
    assert (await team["admin"].delete(f"/users/{users['ed1']}")).status_code == 204
    got = (await team["ed2"].get(f"/reports/{rep['id']}")).json()
    assert got["owner_name"] is None and got["can_edit"] is True


async def test_legacy_items_without_owner_stay_editable(client, monkeypatch):
    """Criado com a autenticação desligada, depois ela é ligada: o item não tem dono e qualquer editor mantém."""
    from app.config import settings
    rep = (await client.post("/reports", json={"title": "antigo", "blocks": []})).json()
    assert rep["owner_name"] is None and rep["can_edit"] is True
    monkeypatch.setattr(settings, "auth_enabled", True)
    await setup_admin(client)
    await make_user(client, "ed1", "editor")
    ed1 = await login("ed1")
    body = {"title": "editado", "blocks": [], "version": rep["version"]}
    assert (await ed1.put(f"/reports/{rep['id']}", json=body)).status_code == 200
