import pytest

from app import datasets, queries
from app.config import settings
from conftest import SALES_CSV, upload


async def q(client, sql, **kw):
    return await client.post("/queries/run", json={"sql": sql, **kw})


async def test_aggregate_and_nulls_and_dates_serialize(client):
    await upload(client, SALES_CSV)
    r = await q(client, "SELECT regiao, sum(receita) AS total, count(*) AS n, min(dia) AS primeiro FROM vendas GROUP BY regiao ORDER BY regiao")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["name"] for c in body["columns"]] == ["regiao", "total", "n", "primeiro"]
    assert body["rows"] == [["Norte", 15.25, 2, "2024-01-03"], ["Sul", 30.5, 2, "2024-01-01"]]
    assert body["truncated"] is False


async def test_join_across_datasets_and_cte(client):
    await upload(client, SALES_CSV, "vendas.csv")
    await upload(client, "regiao,gerente\nSul,Ana\nNorte,Bia\n", "gerentes.csv")
    r = await q(client, "WITH t AS (SELECT regiao, count(*) n FROM vendas GROUP BY 1) SELECT g.gerente, t.n FROM t JOIN gerentes g USING (regiao) ORDER BY 1")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [["Ana", 2], ["Bia", 2]]


async def test_nan_inf_decimal_are_json_safe(client):
    r = await q(client, "SELECT 'nan'::DOUBLE AS a, 'inf'::DOUBLE AS b, 1.5::DECIMAL(3,1) AS c, TIMESTAMP '2020-01-02 03:04:05' AS d")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [[None, None, 1.5, "2020-01-02T03:04:05"]]


async def test_row_limit_truncates(client):
    await upload(client, "x\n" + "\n".join(str(i) for i in range(25)), "n.csv")
    body = (await q(client, "SELECT * FROM n", limit=10)).json()
    assert body["row_count"] == 10 and body["truncated"] is True


async def test_server_limit_caps_client_limit(client, monkeypatch):
    await upload(client, "x\n" + "\n".join(str(i) for i in range(25)), "n.csv")
    monkeypatch.setattr(settings, "query_row_limit", 5)
    body = (await q(client, "SELECT * FROM n", limit=1000)).json()
    assert body["row_count"] == 5 and body["truncated"] is True


async def test_trailing_semicolon_and_line_comment_are_ok(client):
    await upload(client, SALES_CSV)
    r = await q(client, "SELECT count(*) FROM vendas; -- depois\n")
    assert r.status_code == 200 and r.json()["rows"] == [[4]]
    r = await q(client, "SELECT count(*) FROM vendas -- comentário sem quebra de linha")
    assert r.status_code == 200 and r.json()["rows"] == [[4]]


@pytest.mark.parametrize("sql", [
    "SELECT 1; SELECT 2",
    "DROP VIEW vendas",
    "CREATE TABLE t AS SELECT 1",
    "INSERT INTO vendas VALUES (1)",
    "COPY (SELECT 1) TO '/tmp/x.csv'",
    "ATTACH '/tmp/y.db'",
    "PRAGMA database_list",
    "INSTALL httpfs",
    "SET enable_external_access=true",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_parquet('/etc/passwd')",
    "SELECT * FROM range(1000000000)",
    "SELECT * FROM '/etc/passwd'",
    "SELEC oops",
])
async def test_forbidden_or_invalid_sql_is_422(client, sql):
    await upload(client, SALES_CSV)
    r = await q(client, sql)
    assert r.status_code == 422, (sql, r.text)


@pytest.mark.parametrize("sql", [
    'SELECT * FROM "/etc/passwd"',                     # replacement scan: o parser vê um identificador comum
    'SELECT * FROM "/etc/passwd.csv"',
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM information_schema.schemata WHERE 1=0 UNION ALL SELECT * FROM read_text('/etc/passwd')",
])
async def test_sandbox_blocks_what_the_parser_cannot_see(client, sql):
    """Camada 2: mesmo se passar pela validação de AST, o DuckDB travado não pode tocar arquivos."""
    await upload(client, SALES_CSV)
    r = await q(client, sql)
    assert r.status_code == 422, (sql, r.text)
    assert "root:" not in r.text  # nunca vaza conteúdo


async def test_cannot_read_unregistered_parquet_even_in_data_dir(client):
    """Um Parquet no data_dir que não é dataset registrado não está em allowed_paths."""
    import duckdb
    ds = await upload(client, SALES_CSV)
    stray = settings.data_dir / "datasets" / "stray.parquet"
    duckdb.connect().execute(f"COPY (SELECT 'segredo' AS s) TO '{stray}' (FORMAT parquet)")
    r = await q(client, f'SELECT * FROM "{stray}"')
    assert r.status_code == 422 and "segredo" not in r.text


async def test_timeout_interrupts_runaway_query(client):
    await upload(client, "x\n" + "\n".join(str(i) for i in range(2000)), "n.csv")
    heavy = "SELECT count(*) FROM n a, n b, n c, n d, n e, n f"  # 2000^6 linhas
    with pytest.raises(queries.QueryError, match="time limit"):
        queries.run_query(heavy, timeout_s=0.5)
    r = await q(client, "SELECT count(*) FROM n")  # serviço continua saudável
    assert r.status_code == 200 and r.json()["rows"] == [[2000]]
