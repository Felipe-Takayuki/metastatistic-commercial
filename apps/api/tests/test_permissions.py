import sqlite3

import pytest
from conftest import SALES_CSV
from test_auth import auth_on, login, make_user, setup_admin  # noqa: F401

from app.config import settings

REGIOES = "id,regiao,valor\n1,Sul,10\n2,Sul,20\n3,Norte,30\n4,Leste,40\n5,Norte,50\n"


@pytest.fixture
async def team(client, auth_on):
    await setup_admin(client)
    ids = {}
    for name, role in [("dona", "editor"), ("amigo", "viewer"), ("alheio", "viewer"), ("outro", "editor")]:
        ids[name] = (await make_user(client, name, role))["id"]
    c = {"admin": client}
    for n in ids:
        c[n] = await login(n)
    return c, ids


async def upload(c, csv=SALES_CSV, name="v.csv"):
    r = await c.post("/datasets", files={"file": (name, csv.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


async def sql(c, text):
    return await c.post("/queries/run", json={"sql": text})


async def set_access(c, ds, **cfg):
    return await c.put(f"/datasets/{ds['id']}/access", json={"restricted": False, "user_ids": [], "rls": None, **cfg})


async def set_attrs(admin, uid, attrs):
    r = await admin.patch(f"/users/{uid}", json={"attributes": attrs})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- acesso por dataset ----------

async def test_open_by_default(team):
    c, _ = team
    ds = await upload(c["dona"])
    assert ds["restricted"] is False
    assert (await c["alheio"].get(f"/datasets/{ds['id']}")).status_code == 200
    assert (await sql(c["alheio"], f'SELECT COUNT(*) FROM "{ds["table_name"]}"')).json()["rows"] == [[4]]


async def test_restricted_dataset_is_invisible_to_others(team):
    c, ids = team
    ds = await upload(c["dona"])
    assert (await set_access(c["dona"], ds, restricted=True, user_ids=[ids["amigo"]])).status_code == 200
    t = ds["table_name"]
    for who, sees in [("dona", True), ("amigo", True), ("admin", True), ("alheio", False), ("outro", False)]:
        listed = {d["id"] for d in (await c[who].get("/datasets")).json()}
        assert (ds["id"] in listed) is sees, who
        assert (await c[who].get(f"/datasets/{ds['id']}")).status_code == (200 if sees else 404), who
        assert (await c[who].get(f"/datasets/{ds['id']}/preview")).status_code == (200 if sees else 404), who
        q = await sql(c[who], f'SELECT COUNT(*) FROM "{t}"')
        assert q.status_code == (200 if sees else 422), who  # a tabela nem existe para quem não lê
        a = await c[who].post("/analyses/run", json={"analysis": "Descriptives", "dataset_id": ds["id"], "options": {}})
        assert (a.status_code == 404) is (not sees), who  # quem pode ler passa da checagem (e esbarra no motor, ausente nos testes)
    assert (await c["amigo"].get(f"/datasets/{ds['id']}")).json()["restricted"] is True


async def test_only_owner_or_admin_configures_access(team):
    c, ids = team
    ds = await upload(c["dona"])
    assert (await c["outro"].put(f"/datasets/{ds['id']}/access", json={"restricted": True})).status_code == 403
    assert (await c["amigo"].get(f"/datasets/{ds['id']}/access")).status_code == 403
    assert (await set_access(c["dona"], ds, restricted=True)).status_code == 200
    assert (await c["admin"].get(f"/datasets/{ds['id']}/access")).json()["restricted"] is True
    bad = await set_access(c["dona"], ds, restricted=True, user_ids=["nao-existe"])
    assert bad.status_code == 422
    bad = await set_access(c["dona"], ds, rls={"column": "nao_existe", "attribute": "regiao"})
    assert bad.status_code == 422
    bad = await set_access(c["dona"], ds, rls={"column": "regiao", "attribute": "Nome Ruim"})
    assert bad.status_code == 422


async def test_derived_dataset_inherits_restriction(team):
    c, ids = team
    src = await upload(c["dona"])
    await set_access(c["dona"], src, restricted=True, user_ids=[ids["amigo"], ids["outro"]])
    r = await c["outro"].post("/datasets/from-query", json={"name": "copia", "sql": f'SELECT * FROM "{src["table_name"]}"'})
    assert r.status_code == 201
    derived = r.json()
    assert derived["restricted"] is True
    assert (await c["alheio"].get(f"/datasets/{derived['id']}")).status_code == 404  # a cópia não vaza
    # a lista da cópia = a da fonte
    cfg = (await c["admin"].get(f"/datasets/{derived['id']}/access")).json()
    assert sorted(cfg["user_ids"]) == sorted([ids["amigo"], ids["outro"]])


async def test_derived_from_open_dataset_stays_open(team):
    c, _ = team
    src = await upload(c["dona"])
    d = (await c["dona"].post("/datasets/from-query", json={"name": "copia", "sql": f'SELECT * FROM "{src["table_name"]}"'})).json()
    assert d["restricted"] is False


async def test_deleting_dataset_removes_access_rows(team):
    c, ids = team
    ds = await upload(c["dona"], REGIOES)
    await set_access(c["dona"], ds, restricted=True, user_ids=[ids["amigo"]], rls={"column": "regiao", "attribute": "regiao"})
    await set_attrs(c["admin"], ids["amigo"], {"regiao": "Sul"})
    await sql(c["amigo"], f'SELECT * FROM "{ds["table_name"]}"')
    assert (await c["dona"].delete(f"/datasets/{ds['id']}")).status_code == 204
    con = sqlite3.connect(settings.data_dir / "meta.db")
    for table in ("dataset_acl", "dataset_grants", "dataset_rls", "rls_views"):
        assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert not list((settings.data_dir / "datasets").glob("*.parquet"))


# ---------- segurança por linha ----------

async def rls_dataset(c, ids):
    ds = await upload(c["dona"], REGIOES, "regioes.csv")
    r = await set_access(c["dona"], ds, rls={"column": "regiao", "attribute": "regiao"})
    assert r.status_code == 200
    await set_attrs(c["admin"], ids["amigo"], {"regiao": "Sul"})
    await set_attrs(c["admin"], ids["outro"], {"regiao": "Norte, Leste"})
    return ds


async def test_row_level_security_in_sql_and_preview(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    t = ds["table_name"]
    counts = {}
    for who in ("dona", "admin", "amigo", "outro", "alheio"):
        counts[who] = (await sql(c[who], f'SELECT COUNT(*) FROM "{t}"')).json()["rows"][0][0]
    assert counts == {"dona": 5, "admin": 5, "amigo": 2, "outro": 3, "alheio": 0}  # dono e admin veem tudo; sem atributo, nada
    assert (await sql(c["amigo"], f'SELECT DISTINCT regiao FROM "{t}"')).json()["rows"] == [["Sul"]]
    assert (await c["outro"].get(f"/datasets/{ds['id']}/preview")).json()["row_count"] == 3
    assert (await c["amigo"].get(f"/datasets/{ds['id']}")).json()["row_filtered"] is True
    assert (await c["dona"].get(f"/datasets/{ds['id']}")).json()["row_filtered"] is False


async def test_row_filter_cannot_be_bypassed_with_sql_tricks(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    t = ds["table_name"]
    for text in [f'SELECT * FROM "{t}" UNION ALL SELECT * FROM "{t}" WHERE 1=1',
                 f"SELECT * FROM read_parquet('{settings.data_dir}/datasets/{ds['id']}.parquet')",
                 f"SELECT * FROM '{settings.data_dir}/datasets/{ds['id']}.parquet'",
                 "SELECT * FROM glob('/**')", "SELECT * FROM duckdb_views()"]:
        r = await sql(c["amigo"], text)
        if r.status_code == 200:  # consulta válida: só as linhas dele
            assert "Norte" not in str(r.json()) and "Leste" not in str(r.json()), text
        else:
            assert r.status_code == 422, text


async def test_changing_user_attribute_changes_what_they_see(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    t = ds["table_name"]
    await set_attrs(c["admin"], ids["amigo"], {"regiao": "Leste"})
    assert (await sql(c["amigo"], f'SELECT id FROM "{t}"')).json()["rows"] == [[4]]
    await set_attrs(c["admin"], ids["amigo"], {})
    assert (await sql(c["amigo"], f'SELECT COUNT(*) FROM "{t}"')).json()["rows"] == [[0]]


async def test_removing_the_rule_shows_everything_again(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    await set_access(c["dona"], ds)  # sem rls
    assert (await sql(c["amigo"], f'SELECT COUNT(*) FROM "{ds["table_name"]}"')).json()["rows"] == [[5]]
    assert (await c["amigo"].get(f"/datasets/{ds['id']}")).json()["row_filtered"] is False


async def test_derived_from_row_filtered_is_owner_only(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    r = await c["dona"].post("/datasets/from-query", json={"name": "completa", "sql": f'SELECT * FROM "{ds["table_name"]}"'})
    d = r.json()
    assert d["restricted"] is True and d["n_rows"] == 5
    for who in ("amigo", "outro", "alheio"):  # uma cópia completa NÃO pode abrir as linhas filtradas
        assert (await c[who].get(f"/datasets/{d['id']}")).status_code == 404, who
    assert (await c["admin"].get(f"/datasets/{d['id']}/access")).json()["user_ids"] == []


async def test_derived_by_filtered_user_only_has_their_rows(team):
    c, ids = team
    ds = await rls_dataset(c, ids)
    # "outro" é editor com atributo Norte,Leste: a cópia dele só tem as linhas dele
    d = (await c["outro"].post("/datasets/from-query", json={"name": "minha", "sql": f'SELECT * FROM "{ds["table_name"]}"'})).json()
    assert d["n_rows"] == 3 and d["restricted"] is True


async def test_filtered_parquet_for_analyses(team):
    from app import auth, datasets, permissions
    c, ids = team
    ds = await rls_dataset(c, ids)
    amigo = auth.get_user(ids["amigo"])
    dona = auth.get_user((await c["dona"].get("/auth/me")).json()["id"])
    d = datasets.get_dataset(ds["id"])
    assert permissions.analysis_source(dona, d) == ds["id"]  # quem vê tudo lê o original
    view = permissions.analysis_source(amigo, d)
    assert view != ds["id"] and len(view) == 32
    assert datasets.describe_parquet(datasets.parquet_path(view))[0] == 2
    assert permissions.analysis_source(amigo, d) == view  # reaproveita
    await set_attrs(c["admin"], ids["amigo"], {"regiao": "Norte"})
    assert permissions.analysis_source(amigo, d) != view  # outro atributo, outra cópia


async def test_analysis_payload_uses_filtered_source_and_separate_cache_key(team, monkeypatch):
    from app import analysis_service
    c, ids = team
    ds = await rls_dataset(c, ids)
    seen = []

    async def fake_run(self, key, payload):
        seen.append((key, payload["dataset_id"]))
        return {"status": "complete", "results": {}}

    monkeypatch.setattr(analysis_service.AnalysisService, "run", fake_run)
    body = {"analysis": "Descriptives", "dataset_id": ds["id"], "options": {}}
    await c["dona"].post("/analyses/run", json=body)
    await c["amigo"].post("/analyses/run", json=body)
    (k1, d1), (k2, d2) = seen
    assert d1 == ds["id"] and d2 != ds["id"] and k1 != k2  # o motor lê a cópia filtrada; o cache não mistura usuários


# ---------- atributos ----------

async def test_attribute_validation_and_directory(team):
    c, ids = team
    bad = await c["admin"].patch(f"/users/{ids['amigo']}", json={"attributes": {"Nome Ruim": "x"}})
    assert bad.status_code == 422
    ok = await set_attrs(c["admin"], ids["amigo"], {"Regiao": " Sul ,  Norte,, "})
    assert ok["attributes"] == {"regiao": "Sul,Norte"}
    assert {u["username"] for u in (await c["admin"].get("/users")).json() if u["attributes"]} == {"amigo"}
    d = await c["dona"].get("/auth/directory")
    assert d.status_code == 200 and all(set(u) == {"id", "username", "display_name"} for u in d.json())
    assert (await c["amigo"].get("/auth/directory")).status_code == 403  # leitor não lista usuários


async def test_deleting_user_removes_attributes_and_grants(team):
    c, ids = team
    ds = await upload(c["dona"])
    await set_access(c["dona"], ds, restricted=True, user_ids=[ids["amigo"]])
    await set_attrs(c["admin"], ids["amigo"], {"regiao": "Sul"})
    await c["admin"].delete(f"/users/{ids['amigo']}")
    con = sqlite3.connect(settings.data_dir / "meta.db")
    assert con.execute("SELECT COUNT(*) FROM user_attributes").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM dataset_grants").fetchone()[0] == 0
