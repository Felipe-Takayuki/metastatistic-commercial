"""Receitas de transformação: cada passo é conferido contra um cálculo independente em Python."""
import statistics

import pytest
from conftest import SALES_CSV
from test_auth import auth_on, login, make_user, setup_admin  # noqa: F401

CSV = (
    "id,grupo,nota1,nota2,nota3,data,texto\n"
    "1,A,7,8,9,2024-01-15,  Ana \n"
    "2,A,5,,6,2024-02-20,bia\n"
    "3,B,10,10,10,2024-03-25,CARLOS\n"
    "4,B,,4,6,2024-04-30,ana\n"
    "5,A,6,7,8,2024-01-15,Dora\n"
    "6,B,3,5,,2024-12-01,eva\n"
    "5,A,6,7,8,2024-01-15,Dora\n"
)
ROWS = [
    dict(id=1, grupo="A", nota1=7, nota2=8, nota3=9, data="2024-01-15", texto="  Ana "),
    dict(id=2, grupo="A", nota1=5, nota2=None, nota3=6, data="2024-02-20", texto="bia"),
    dict(id=3, grupo="B", nota1=10, nota2=10, nota3=10, data="2024-03-25", texto="CARLOS"),
    dict(id=4, grupo="B", nota1=None, nota2=4, nota3=6, data="2024-04-30", texto="ana"),
    dict(id=5, grupo="A", nota1=6, nota2=7, nota3=8, data="2024-01-15", texto="Dora"),
    dict(id=6, grupo="B", nota1=3, nota2=5, nota3=None, data="2024-12-01", texto="eva"),
    dict(id=5, grupo="A", nota1=6, nota2=7, nota3=8, data="2024-01-15", texto="Dora"),
]


async def upload(c, csv=CSV, name="notas.csv"):
    r = await c.post("/datasets", files={"file": (name, csv.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
async def ds(client):
    return await upload(client)


async def run(client, ds, *steps, limit=100):
    r = await client.post("/transforms/preview", json={"recipe": {"source_id": ds["id"], "steps": list(steps)}, "limit": limit})
    return r


async def table(client, ds, *steps):
    r = await run(client, ds, *steps)
    assert r.status_code == 200, r.text
    body = r.json()
    names = [c["name"] for c in body["columns"]]
    return [dict(zip(names, row)) for row in body["rows"]], body


def col(rows, name):
    return [r[name] for r in rows]


def close(a, b):
    return len(a) == len(b) and all((x is None and y is None) or (x is not None and y is not None and abs(x - y) < 1e-9) for x, y in zip(a, b))


# ---------- passos de coluna ----------

async def test_no_steps_is_identity(client, ds):
    rows, body = await table(client, ds)
    assert len(rows) == 7 and body["total_rows"] == 7 and body["sql"].startswith("WITH __s0")
    assert [len(s) for s in body["schemas"]] == [7]


async def test_select_keep_drop_and_rename(client, ds):
    rows, _ = await table(client, ds, {"op": "select", "columns": ["nota2", "id"]})
    assert list(rows[0]) == ["nota2", "id"]  # a ordem escolhida vale
    rows, _ = await table(client, ds, {"op": "select", "columns": ["texto", "data"], "mode": "drop"})
    assert "texto" not in rows[0] and "data" not in rows[0] and len(rows[0]) == 5
    rows, _ = await table(client, ds, {"op": "rename", "mapping": {"nota1": "prova1", "grupo": "turma"}})
    assert list(rows[0])[:3] == ["id", "turma", "prova1"] and rows[0]["prova1"] == 7


async def test_cast_invalid_values_become_null(client, ds):
    rows, body = await table(client, ds, {"op": "cast", "column": "texto", "to": "number"})
    assert all(v is None for v in col(rows, "texto"))
    assert [c for c in body["columns"] if c["name"] == "texto"][0]["dtype"] == "DOUBLE"
    rows, _ = await table(client, ds, {"op": "cast", "column": "id", "to": "text"})
    assert col(rows, "id")[:2] == ["1", "2"]


async def test_filter_operators_and_combine(client, ds):
    f = lambda *conds, combine="and": {"op": "filter", "conditions": list(conds), "combine": combine}  # noqa: E731
    rows, body = await table(client, ds, f({"column": "grupo", "operator": "eq", "value": "A"}, {"column": "nota1", "operator": "ge", "value": "6"}))
    assert sorted(col(rows, "id")) == [1, 5, 5] and body["total_rows"] == 3
    rows, _ = await table(client, ds, f({"column": "grupo", "operator": "eq", "value": "B"}, {"column": "nota2", "operator": "lt", "value": "5"}, combine="or"))
    assert sorted(col(rows, "id")) == [3, 4, 6]
    rows, _ = await table(client, ds, f({"column": "texto", "operator": "contains", "value": "AN"}))
    assert sorted(col(rows, "id")) == [1, 4]  # sem diferenciar maiúsculas
    rows, _ = await table(client, ds, f({"column": "texto", "operator": "starts_with", "value": "c"}))
    assert col(rows, "id") == [3]
    rows, _ = await table(client, ds, f({"column": "nota1", "operator": "is_null"}))
    assert col(rows, "id") == [4]
    rows, _ = await table(client, ds, f({"column": "nota2", "operator": "not_null"}, {"column": "grupo", "operator": "in", "values": ["B"]}))
    assert sorted(col(rows, "id")) == [3, 4, 6]
    rows, _ = await table(client, ds, f({"column": "data", "operator": "gt", "value": "2024-03-01"}))
    assert sorted(col(rows, "id")) == [3, 4, 6]
    rows, _ = await table(client, ds, f({"column": "nota1", "operator": "eq", "value": "7,0"}))  # vírgula decimal
    assert col(rows, "id") == [1]


async def test_sort_stable_nulls_last(client, ds):
    rows, _ = await table(client, ds, {"op": "sort", "keys": [{"column": "nota1", "desc": True}]})
    assert col(rows, "nota1") == [10, 7, 6, 6, 5, 3, None]
    rows, _ = await table(client, ds, {"op": "sort", "keys": [{"column": "grupo"}, {"column": "id", "desc": True}]})
    assert col(rows, "id") == [5, 5, 2, 1, 6, 4, 3]


async def test_dedupe_keeps_first_and_original_order(client, ds):
    rows, _ = await table(client, ds, {"op": "dedupe"})
    assert col(rows, "id") == [1, 2, 3, 4, 5, 6]  # a linha repetida some e a ordem não muda
    rows, _ = await table(client, ds, {"op": "dedupe", "columns": ["grupo"]})
    assert col(rows, "id") == [1, 3]  # primeira linha de cada grupo, na ordem de aparição


async def test_drop_nulls(client, ds):
    rows, _ = await table(client, ds, {"op": "drop_nulls", "columns": ["nota1"]})
    assert 4 not in col(rows, "id") and len(rows) == 6
    rows, _ = await table(client, ds, {"op": "drop_nulls"})
    assert sorted(set(col(rows, "id"))) == [1, 3, 5]  # linhas completas


async def test_fill_nulls_value_mean_median(client, ds):
    n2 = [r["nota2"] for r in ROWS]
    known = [x for x in n2 if x is not None]
    rows, _ = await table(client, ds, {"op": "fill_nulls", "column": "nota2", "how": "value", "value": "0"})
    assert col(rows, "nota2") == [x if x is not None else 0 for x in n2]
    rows, _ = await table(client, ds, {"op": "fill_nulls", "column": "nota2", "how": "mean"})
    assert close(col(rows, "nota2"), [x if x is not None else statistics.fmean(known) for x in n2])
    rows, _ = await table(client, ds, {"op": "fill_nulls", "column": "nota2", "how": "median"})
    assert close(col(rows, "nota2"), [x if x is not None else statistics.median(known) for x in n2])
    rows, _ = await table(client, ds, {"op": "fill_nulls", "column": "texto", "how": "value", "value": "x"})
    assert "x" not in col(rows, "texto")  # texto não tem nulos: nada muda


# ---------- colunas calculadas ----------

async def test_row_mean_ignores_nulls_and_require_all(client, ds):
    cols = ["nota1", "nota2", "nota3"]

    def ref(r, need_all=False):
        vals = [r[c] for c in cols]
        if need_all and None in vals:
            return None
        vals = [v for v in vals if v is not None]
        return statistics.fmean(vals) if vals else None

    rows, _ = await table(client, ds, {"op": "row_stat", "name": "media", "fn": "mean", "columns": cols})
    assert close(col(rows, "media"), [ref(r) for r in ROWS])  # (7+8+9)/3 = 8; linha 4 = (4+6)/2 = 5
    assert col(rows, "media")[3] == 5
    rows, _ = await table(client, ds, {"op": "row_stat", "name": "media", "fn": "mean", "columns": cols, "require_all": True})
    assert close(col(rows, "media"), [ref(r, True) for r in ROWS])
    for fn, ref_fn in [("sum", sum), ("min", min), ("max", max)]:
        rows, _ = await table(client, ds, {"op": "row_stat", "name": "x", "fn": fn, "columns": cols})
        assert close(col(rows, "x"), [ref_fn(v for v in (r[c] for c in cols) if v is not None) for r in ROWS]), fn
    rows, _ = await table(client, ds, {"op": "row_stat", "name": "n", "fn": "count", "columns": cols})
    assert col(rows, "n") == [sum(r[c] is not None for c in cols) for r in ROWS]


async def test_arith_with_columns_numbers_and_zero_division(client, ds):
    rows, _ = await table(client, ds, {"op": "arith", "name": "soma", "left": {"col": "nota1"}, "operator": "+", "right": {"col": "nota2"}})
    assert col(rows, "soma") == [None if r["nota1"] is None or r["nota2"] is None else r["nota1"] + r["nota2"] for r in ROWS]
    rows, _ = await table(client, ds, {"op": "arith", "name": "pct", "left": {"col": "nota1"}, "operator": "/", "right": {"num": 10}})
    assert close(col(rows, "pct"), [None if r["nota1"] is None else r["nota1"] / 10 for r in ROWS])
    rows, _ = await table(client, ds, {"op": "arith", "name": "z", "left": {"col": "nota1"}, "operator": "/", "right": {"num": 0}})
    assert all(v is None for v in col(rows, "z"))  # divisão por zero vira nulo, não erro


async def test_math_functions_and_domain_errors_are_null(client, ds):
    rows, _ = await table(client, ds, {"op": "arith", "name": "neg", "left": {"col": "nota1"}, "operator": "-", "right": {"num": 6}},
                          {"op": "math", "name": "raiz", "fn": "sqrt", "column": "neg"})
    assert col(rows, "raiz") == [None if r["nota1"] is None or r["nota1"] < 6 else (r["nota1"] - 6) ** 0.5 for r in ROWS]
    rows, _ = await table(client, ds, {"op": "math", "name": "l", "fn": "log10", "column": "nota1"})
    import math
    assert close(col(rows, "l"), [None if r["nota1"] is None else math.log10(r["nota1"]) for r in ROWS])
    rows, _ = await table(client, ds, {"op": "arith", "name": "m", "left": {"col": "nota1"}, "operator": "/", "right": {"num": 3}},
                          {"op": "math", "name": "r", "fn": "round", "column": "m", "digits": 2})
    assert close(col(rows, "r"), [None if r["nota1"] is None else round(r["nota1"] / 3, 2) for r in ROWS])


async def test_conditional_column(client, ds):
    step = {"op": "cond", "name": "situacao", "conditions": [{"column": "nota1", "operator": "ge", "value": "6"}], "then": {"text": "aprovado"}, "otherwise": {"text": "reprovado"}}
    rows, _ = await table(client, ds, step)
    assert col(rows, "situacao") == ["aprovado" if (r["nota1"] or -1) >= 6 else "reprovado" for r in ROWS]  # nulo cai no "senão"
    step = {"op": "cond", "name": "m", "conditions": [{"column": "grupo", "operator": "eq", "value": "A"}], "then": {"col": "nota1"}, "otherwise": {"num": 0}}
    rows, _ = await table(client, ds, step)
    assert col(rows, "m") == [r["nota1"] if r["grupo"] == "A" else 0 for r in ROWS]


async def test_bins_with_auto_and_custom_labels(client, ds):
    rows, _ = await table(client, ds, {"op": "bins", "name": "faixa", "column": "nota1", "edges": [5, 8]})
    def ref(v):
        return None if v is None else "< 5" if v < 5 else "5 – 8" if v < 8 else "≥ 8"
    assert col(rows, "faixa") == [ref(r["nota1"]) for r in ROWS]
    rows, _ = await table(client, ds, {"op": "bins", "name": "faixa", "column": "nota1", "edges": [5, 8], "labels": ["baixa", "média", "alta"]})
    assert col(rows, "faixa")[0] == "média" and col(rows, "faixa")[2] == "alta" and col(rows, "faixa")[5] == "baixa"
    bad = await run(client, ds, {"op": "bins", "name": "f", "column": "nota1", "edges": [5, 8], "labels": ["a", "b"]})
    assert bad.status_code == 422 and "3 rótulos" in bad.json()["detail"]
    assert (await run(client, ds, {"op": "bins", "name": "f", "column": "nota1", "edges": [8, 5]})).status_code == 422  # limites crescentes


async def test_replace_in_place_and_new_column(client, ds):
    rows, _ = await table(client, ds, {"op": "replace", "column": "grupo", "mapping": {"A": "Turma 1", "B": "Turma 2"}})
    assert col(rows, "grupo") == ["Turma 1" if r["grupo"] == "A" else "Turma 2" for r in ROWS] and list(rows[0])[1] == "grupo"
    rows, _ = await table(client, ds, {"op": "replace", "name": "g2", "column": "grupo", "mapping": {"A": "x"}})
    assert col(rows, "g2") == ["x" if r["grupo"] == "A" else "B" for r in ROWS] and col(rows, "grupo")[0] == "A"


async def test_text_concat_and_date_parts(client, ds):
    rows, _ = await table(client, ds, {"op": "text_fn", "name": "t", "fn": "trim", "column": "texto"}, {"op": "text_fn", "name": "u", "fn": "upper", "column": "t"},
                          {"op": "text_fn", "name": "n", "fn": "length", "column": "t"})
    assert col(rows, "u") == [r["texto"].strip().upper() for r in ROWS] and col(rows, "n") == [len(r["texto"].strip()) for r in ROWS]
    rows, _ = await table(client, ds, {"op": "concat", "name": "c", "columns": ["grupo", "id"], "sep": "-"})
    assert col(rows, "c") == [f"{r['grupo']}-{r['id']}" for r in ROWS]
    rows, _ = await table(client, ds, {"op": "date_part", "name": "ano", "column": "data", "part": "year"},
                          {"op": "date_part", "name": "mes", "column": "data", "part": "month"},
                          {"op": "date_part", "name": "tri", "column": "data", "part": "quarter"},
                          {"op": "date_part", "name": "ym", "column": "data", "part": "year_month"},
                          {"op": "date_part", "name": "dow", "column": "data", "part": "weekday"})
    import datetime as dt
    dates = [dt.date.fromisoformat(r["data"]) for r in ROWS]
    assert col(rows, "ano") == [d.year for d in dates] and col(rows, "mes") == [d.month for d in dates]
    assert col(rows, "tri") == [(d.month - 1) // 3 + 1 for d in dates] and col(rows, "ym") == [d.strftime("%Y-%m") for d in dates]
    assert col(rows, "dow") == [d.isoweekday() for d in dates]


async def test_formula_valid_and_case_insensitive_columns(client, ds):
    rows, _ = await table(client, ds, {"op": "formula", "name": "f", "expr": "ROUND((NOTA1 + nota2) / 2.0, 1)"})
    assert close(col(rows, "f"), [None if r["nota1"] is None or r["nota2"] is None else round((r["nota1"] + r["nota2"]) / 2, 1) for r in ROWS])
    rows, _ = await table(client, ds, {"op": "formula", "name": "g", "expr": "CASE WHEN nota3 >= 8 THEN 'ok' ELSE 'não' END"})
    assert col(rows, "g") == ["ok" if (r["nota3"] or 0) >= 8 else "não" for r in ROWS]
    rows, _ = await table(client, ds, {"op": "formula", "name": "h", "expr": "coalesce(nota1, 0) * 2"})
    assert col(rows, "h") == [(r["nota1"] or 0) * 2 for r in ROWS]


@pytest.mark.parametrize("expr", [
    "(SELECT COUNT(*) FROM notas)", "read_csv('/etc/passwd')", "nota1; DROP TABLE notas", "nota1 + 1, 2", "*", "outra_coluna + 1",
    "notas.nota1 + 1", "AVG(nota1) OVER ()", "SUM(nota1)", "nota1 AS x", "nota1::INTERVAL", "CAST(nota1 AS STRUCT(a INT))", "file_exists('x')",
    "list_avg([nota1, nota2])", "unnest([1,2])",
])
async def test_formula_rejects_anything_outside_the_allowlist(client, ds, expr):
    r = await run(client, ds, {"op": "formula", "name": "f", "expr": expr})
    assert r.status_code == 422, expr
    assert "Passo 1" in r.json()["detail"]


# ---------- encadeamento, erros e limites ----------

async def test_steps_chain_and_report_the_failing_step(client, ds):
    steps = [{"op": "filter", "conditions": [{"column": "grupo", "operator": "eq", "value": "A"}]},
             {"op": "row_stat", "name": "media", "fn": "mean", "columns": ["nota1", "nota2", "nota3"]},
             {"op": "select", "columns": ["id", "media"]},
             {"op": "sort", "keys": [{"column": "media", "desc": True}]}]
    rows, body = await table(client, ds, *steps)
    assert col(rows, "id") == [1, 5, 5, 2] and [len(s) for s in body["schemas"]] == [7, 7, 8, 2, 2]
    bad = await run(client, ds, steps[0], {"op": "select", "columns": ["id"]}, {"op": "sort", "keys": [{"column": "nota1"}]})
    assert bad.status_code == 422 and bad.json()["detail"].startswith("Passo 3 (sort): coluna não encontrada: 'nota1'")


@pytest.mark.parametrize("step, fragment", [
    ({"op": "row_stat", "name": "x", "fn": "mean", "columns": ["nota1", "grupo"]}, "não é numérica"),
    ({"op": "row_stat", "name": "id", "fn": "mean", "columns": ["nota1", "nota2"]}, "já existe uma coluna"),
    ({"op": "row_stat", "name": "ID", "fn": "mean", "columns": ["nota1", "nota2"]}, "já existe uma coluna"),
    ({"op": "date_part", "name": "a", "column": "texto", "part": "year"}, "não é uma data"),
    ({"op": "filter", "conditions": [{"column": "nota1", "operator": "gt", "value": "abc"}]}, "não é um número"),
    ({"op": "filter", "conditions": [{"column": "data", "operator": "gt", "value": "ontem"}]}, "data válida"),
    ({"op": "filter", "conditions": [{"column": "grupo", "operator": "in", "values": []}]}, "ao menos um valor"),
    ({"op": "rename", "mapping": {"nota1": "NOTA2"}}, "repetidos"),
    ({"op": "rename", "mapping": {"nao_existe": "x"}}, "coluna não encontrada"),
    ({"op": "select", "columns": list("x")}, "coluna não encontrada"),
    ({"op": "select", "columns": ["id", "grupo", "nota1", "nota2", "nota3", "data", "texto"], "mode": "drop"}, "todas as colunas"),
    ({"op": "cond", "name": "c", "conditions": [{"column": "nota1", "operator": "gt", "value": "1"}], "then": {"text": "a"}, "otherwise": {"num": 1}}, "mesmo tipo"),
    ({"op": "arith", "name": "a", "left": {"col": "grupo"}, "operator": "+", "right": {"num": 1}}, "não é numérica"),
    ({"op": "fill_nulls", "column": "texto", "how": "mean"}, "não é numérica"),
])
async def test_clear_errors(client, ds, step, fragment):
    r = await run(client, ds, step)
    assert r.status_code == 422, r.text
    assert fragment in r.json()["detail"] and r.json()["detail"].startswith("Passo 1")


async def test_schema_validation_limits(client, ds):
    too_many = [{"op": "dedupe"}] * 51
    assert (await run(client, ds, *too_many)).status_code == 422
    assert (await run(client, ds, {"op": "teleport"})).status_code == 422
    assert (await run(client, ds, {"op": "arith", "name": "a", "left": {"col": "id", "num": 1}, "operator": "+", "right": {"num": 1}})).status_code == 422  # operando ambíguo
    r = await client.post("/transforms/preview", json={"recipe": {"source_id": "nao-existe", "steps": []}})
    assert r.status_code == 422 and "origem não encontrado" in r.json()["detail"]


async def test_hostile_identifiers_and_values_are_escaped(client, ds):
    evil = 'x"; DROP TABLE notas; --'
    r = await run(client, ds, {"op": "rename", "mapping": {"nota1": evil}})
    assert r.status_code == 200 and evil in [c["name"] for c in r.json()["columns"]]
    r = await run(client, ds, {"op": "filter", "conditions": [{"column": "grupo", "operator": "eq", "value": "A' OR '1'='1"}]})
    assert r.status_code == 200 and r.json()["total_rows"] == 0
    r = await run(client, ds, {"op": "replace", "name": "r", "column": "grupo", "mapping": {"A'": "x"}})
    assert r.status_code == 200 and r.json()["rows"][0][-1] == "A"
    r = await run(client, ds, {"op": "cond", "name": "c", "conditions": [{"column": "grupo", "operator": "eq", "value": "A"}], "then": {"text": "'; SELECT 1; --"}, "otherwise": {"null": True}})
    assert r.status_code == 200 and r.json()["rows"][0][-1] == "'; SELECT 1; --"


async def test_preview_limit_and_total(client, ds):
    r = await run(client, ds, limit=3)
    body = r.json()
    assert body["row_count"] == 3 and body["truncated"] is True and body["total_rows"] == 7


# ---------- salvar como dataset ----------

async def test_save_materializes_dataset_and_stores_recipe(client, ds):
    # a pessoa marcou nota1 como ordinal na origem: a escolha sobrevive à transformação
    await client.patch(f"/datasets/{ds['id']}", json={"measurement": {"nota1": "ordinal", "nota2": "scale"}})
    steps = [{"op": "dedupe"}, {"op": "row_stat", "name": "media", "fn": "mean", "columns": ["nota1", "nota2", "nota3"]},
             {"op": "select", "columns": ["id", "grupo", "nota1", "media"]}]
    r = await client.post("/transforms/save", json={"recipe": {"source_id": ds["id"], "steps": steps}, "name": "Com média"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["n_rows"] == 6 and [c["name"] for c in new["columns"]] == ["id", "grupo", "nota1", "media"]
    meas = {c["name"]: c["measurement"] for c in new["columns"]}
    assert meas["nota1"] == "ordinal" and meas["media"] == "scale" and meas["grupo"] == "nominal"
    # o novo dataset é consultável por SQL, como qualquer outro
    q = await client.post("/queries/run", json={"sql": f'SELECT round(avg(media), 4) FROM "{new["table_name"]}"'})
    rows = {r["id"]: r for r in ROWS}
    means = [statistics.fmean([v for v in (rows[i]["nota1"], rows[i]["nota2"], rows[i]["nota3"]) if v is not None]) for i in [1, 2, 3, 4, 5, 6]]
    assert abs(q.json()["rows"][0][0] - round(statistics.fmean(means), 4)) < 1e-9
    rec = (await client.get(f"/transforms/recipes/{new['id']}")).json()
    assert rec["recipe"]["source_id"] == ds["id"] and len(rec["recipe"]["steps"]) == 3 and rec["sql"].startswith("WITH")
    assert (await client.get(f"/transforms/recipes/{ds['id']}")).json() is None  # a origem não veio de receita
    assert (await client.delete(f"/datasets/{new['id']}")).status_code == 204
    assert (await client.get(f"/transforms/recipes/{new['id']}")).json() is None  # excluir leva a receita junto


async def test_save_rejects_bad_recipe_and_empty_result(client, ds):
    bad = await client.post("/transforms/save", json={"recipe": {"source_id": ds["id"], "steps": [{"op": "select", "columns": ["x"]}]}, "name": "n"})
    assert bad.status_code == 422 and "Passo 1" in bad.json()["detail"]
    empty = await client.post("/transforms/save", json={"recipe": {"source_id": ds["id"], "steps": [{"op": "filter", "conditions": [{"column": "id", "operator": "gt", "value": "99"}]}]}, "name": "n"})
    assert empty.status_code == 422 and "no rows" in empty.json()["detail"]
    assert len((await client.get("/datasets")).json()) == 1  # nada ficou pelo caminho


# ---------- permissões ----------

@pytest.fixture
async def team(client, auth_on):
    await setup_admin(client)
    ids = {n: (await make_user(client, n, r))["id"] for n, r in [("dona", "editor"), ("leitor", "viewer"), ("outro", "editor")]}
    return {"admin": client, **{n: await login(n) for n in ids}}, ids


async def test_viewer_previews_but_cannot_save(team):
    c, _ = team
    d = await upload(c["dona"])
    rec = {"source_id": d["id"], "steps": [{"op": "dedupe"}]}
    assert (await c["leitor"].post("/transforms/preview", json={"recipe": rec})).status_code == 200
    assert (await c["leitor"].post("/transforms/save", json={"recipe": rec, "name": "x"})).status_code == 403


async def test_recipe_on_restricted_dataset_is_hidden_and_inherits(team):
    c, ids = team
    d = await upload(c["dona"])
    await c["dona"].put(f"/datasets/{d['id']}/access", json={"restricted": True, "user_ids": [ids["outro"]], "rls": None})
    rec = {"source_id": d["id"], "steps": [{"op": "dedupe"}]}
    hidden = await c["leitor"].post("/transforms/preview", json={"recipe": rec})
    assert hidden.status_code == 422 and "origem não encontrado" in hidden.json()["detail"]
    saved = (await c["outro"].post("/transforms/save", json={"recipe": rec, "name": "copia"})).json()
    assert saved["restricted"] is True
    assert (await c["leitor"].get(f"/transforms/recipes/{saved['id']}")).json() is None
    assert (await c["leitor"].get(f"/datasets/{saved['id']}")).status_code == 404


async def test_row_level_security_applies_to_recipes(team):
    c, ids = team
    d = await upload(c["dona"], "id,regiao,valor\n1,Sul,10\n2,Sul,20\n3,Norte,30\n", "r.csv")
    await c["dona"].put(f"/datasets/{d['id']}/access", json={"restricted": False, "user_ids": [], "rls": {"column": "regiao", "attribute": "regiao"}})
    await c["admin"].patch(f"/users/{ids['outro']}", json={"attributes": {"regiao": "Sul"}})
    rec = {"source_id": d["id"], "steps": [{"op": "arith", "name": "dobro", "left": {"col": "valor"}, "operator": "*", "right": {"num": 2}}]}
    mine = (await c["outro"].post("/transforms/preview", json={"recipe": rec})).json()
    assert mine["total_rows"] == 2 and {r[1] for r in mine["rows"]} == {"Sul"}  # só as linhas dele, também na contagem
    assert (await c["dona"].post("/transforms/preview", json={"recipe": rec})).json()["total_rows"] == 3
    saved = (await c["outro"].post("/transforms/save", json={"recipe": rec, "name": "meu"})).json()
    assert saved["n_rows"] == 2 and saved["restricted"] is True  # cópia filtrada: restrita à pessoa e aos administradores


async def test_save_is_audited(team):
    c, _ = team
    d = await upload(c["dona"])
    await c["dona"].post("/transforms/save", json={"recipe": {"source_id": d["id"], "steps": [{"op": "dedupe"}]}, "name": "limpo"})
    ev = [e for e in (await c["admin"].get("/audit")).json() if "receita" in (e["detail"] or "")]
    assert ev and ev[0]["username"] == "dona" and "1 passos" in ev[0]["detail"]
