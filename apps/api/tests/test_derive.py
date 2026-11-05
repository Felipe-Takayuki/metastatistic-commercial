"""Salvar consulta como dataset: POST /datasets/from-query."""
import pytest

from app.config import settings
from conftest import upload

# 8 linhas: 2 tratamentos x 4 blocos "por posição", como no experimento em blocos casualizados do projeto `analise`
DBC_CSV = "trat,y\n" + "\n".join(f"{1 + i // 4},{10 + i * 1.5}" for i in range(8)) + "\n"


async def derive(client, name, sql):
    return await client.post("/datasets/from-query", json={"name": name, "sql": sql})


def parquets():
    return sorted(p.name for p in (settings.data_dir / "datasets").glob("*.parquet"))


async def test_derived_block_column_follows_row_order_and_is_ordinal(client):
    src = await upload(client, DBC_CSV, "dbc.csv")
    r = await derive(client, "dbc com bloco", 'SELECT ((row_number() OVER () - 1) % 4) + 1 AS bloco, * FROM dbc')
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["name"] == "dbc com bloco" and ds["table_name"] == "dbc_com_bloco" and ds["n_rows"] == 8
    cols = {c["name"]: c for c in ds["columns"]}
    assert list(cols) == ["bloco", "trat", "y"]
    assert cols["bloco"]["dtype"] == "BIGINT" and cols["bloco"]["measurement"] == "ordinal" and cols["bloco"]["n_distinct"] == 4
    assert cols["y"]["measurement"] == "scale"
    # a posição da linha foi preservada: o bloco cicla 1,2,3,4 junto com as linhas originais
    rows = (await client.post("/queries/run", json={"sql": "SELECT bloco, trat, y FROM dbc_com_bloco"})).json()["rows"]
    assert [r[0] for r in rows] == [1, 2, 3, 4, 1, 2, 3, 4]
    assert [r[1] for r in rows] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert [r[2] for r in rows] == [10 + i * 1.5 for i in range(8)]
    assert src["id"] != ds["id"]


async def test_transformations_become_real_columns(client):
    await upload(client, DBC_CSV, "dbc.csv")
    ds = (await derive(client, "transf", "SELECT trat, sqrt(y) AS y_sqrt, log10(y) AS y_log FROM dbc")).json()
    cols = {c["name"]: c for c in ds["columns"]}
    assert cols["y_sqrt"]["dtype"] == "DOUBLE" and cols["y_sqrt"]["measurement"] == "scale"
    got = (await client.post("/queries/run", json={"sql": "SELECT y_sqrt FROM transf ORDER BY y_sqrt LIMIT 1"})).json()["rows"][0][0]
    assert got == pytest.approx(10 ** 0.5)


async def test_derived_dataset_is_materialized_and_independent_of_its_source(client):
    src = await upload(client, DBC_CSV, "dbc.csv")
    d = (await derive(client, "copia", "SELECT * FROM dbc")).json()
    assert (await client.delete(f"/datasets/{src['id']}")).status_code == 204
    r = await client.post("/queries/run", json={"sql": "SELECT count(*) FROM copia"})
    assert r.status_code == 200 and r.json()["rows"] == [[8]]  # não é uma view: os dados foram gravados
    assert (await client.get(f"/datasets/{d['id']}/preview")).status_code == 200


async def test_duplicate_column_names_are_made_unique_not_a_500(client):
    await upload(client, DBC_CSV, "dbc.csv")
    r = await derive(client, "dup", "SELECT y AS a, y AS a FROM dbc")
    assert r.status_code == 201
    assert [c["name"] for c in r.json()["columns"]] == ["a", "a_1"]


async def test_name_gets_a_unique_sql_table_name_like_uploads(client):
    await upload(client, DBC_CSV, "dbc.csv")
    a = (await derive(client, "mesmo nome", "SELECT * FROM dbc")).json()
    b = (await derive(client, "mesmo nome", "SELECT * FROM dbc")).json()
    assert a["table_name"] == "mesmo_nome" and b["table_name"] == "mesmo_nome_2"


@pytest.mark.parametrize("sql", [
    "SELECT 1; SELECT 2",
    "DROP VIEW dbc",
    "INSERT INTO dbc VALUES (1, 2)",
    "COPY (SELECT 1) TO '/tmp/hack.csv'",
    "ATTACH '/tmp/y.db'",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM range(10)",
    "SELECT * FROM '/etc/passwd'",
    'SELECT * FROM "/etc/passwd"',
    "SELEC oops",
])
async def test_only_read_only_queries_are_accepted_and_nothing_is_left_behind(client, sql):
    await upload(client, DBC_CSV, "dbc.csv")
    before = parquets()
    r = await derive(client, "mau", sql)
    assert r.status_code == 422, (sql, r.text)
    assert parquets() == before  # nenhum Parquet órfão
    assert [d["name"] for d in (await client.get("/datasets")).json()] == ["dbc.csv"]  # nada registrado
    assert "root:" not in r.text


async def test_user_cannot_choose_where_the_file_is_written(client, tmp_path):
    """O destino é gerado pelo servidor; tentar gravar em outro lugar pelo SQL é bloqueado pelo sandbox."""
    await upload(client, DBC_CSV, "dbc.csv")
    target = tmp_path / "escapou.parquet"
    r = await derive(client, "x", f"COPY (SELECT * FROM dbc) TO '{target}' (FORMAT parquet)")
    assert r.status_code == 422 and not target.exists()


async def test_result_larger_than_the_limit_is_rejected_not_silently_truncated(client, monkeypatch):
    await upload(client, DBC_CSV, "dbc.csv")  # 8 linhas
    monkeypatch.setattr(settings, "derived_dataset_max_rows", 5)
    before = parquets()
    r = await derive(client, "grande", "SELECT * FROM dbc")
    assert r.status_code == 422 and "more than 5" in r.json()["detail"]
    assert parquets() == before
    ok = await derive(client, "cabe", "SELECT * FROM dbc LIMIT 5")  # no limite exato: aceito
    assert ok.status_code == 201 and ok.json()["n_rows"] == 5


async def test_empty_result_is_rejected(client):
    await upload(client, DBC_CSV, "dbc.csv")
    before = parquets()
    r = await derive(client, "vazio", "SELECT * FROM dbc WHERE y > 1e9")
    assert r.status_code == 422 and "no rows" in r.json()["detail"]
    assert parquets() == before


async def test_runaway_query_is_interrupted_and_cleaned_up(client, monkeypatch):
    await upload(client, "x\n" + "\n".join(str(i) for i in range(2000)) + "\n", "n.csv")
    monkeypatch.setattr(settings, "derived_dataset_timeout_s", 0.5)
    before = parquets()
    r = await derive(client, "lento", "SELECT count(*) AS c FROM n a, n b, n c, n d, n e, n f")
    assert r.status_code == 422 and "time limit" in r.json()["detail"]
    assert parquets() == before
    assert (await client.post("/queries/run", json={"sql": "SELECT count(*) FROM n"})).status_code == 200  # serviço saudável


@pytest.mark.parametrize("name", ["", "   "])
async def test_blank_name_is_rejected(client, name):
    await upload(client, DBC_CSV, "dbc.csv")
    assert (await derive(client, name, "SELECT * FROM dbc")).status_code == 422


async def test_derived_dataset_can_feed_an_analysis(client):
    """Ponta a ponta (com worker simulado): a análise recebe o dataset derivado, com a coluna bloco como fator."""
    import httpx
    import respx

    await upload(client, DBC_CSV, "dbc.csv")
    ds = (await derive(client, "dbc bloco", "SELECT ((row_number() OVER () - 1) % 4) + 1 AS bloco, * FROM dbc")).json()
    with respx.mock:
        route = respx.post(f"{settings.r_worker_url}/run").respond(json={"status": "complete", "results": {}})
        r = await client.post("/analyses/run", json={"analysis": "Anova", "dataset_id": ds["id"], "options": {"dependent": "y", "fixedFactors": ["trat", "bloco"]}})
    assert r.status_code == 200
    sent = httpx.Response(200, content=route.calls.last.request.content).json()
    assert sent["dataset_id"] == ds["id"] and sorted(sent["columns"]) == ["bloco", "trat", "y"]
    assert sent["measurement"] == {"bloco": "ordinal", "trat": "ordinal", "y": "scale"}  # bloco e trat viram fator no R
