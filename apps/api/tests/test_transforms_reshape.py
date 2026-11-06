"""Passos que reformatam tabelas (8.4): resumir, pivotar, despivotar, mesclar e acrescentar — conferidos em Python."""
import statistics
from collections import defaultdict

import pytest
from conftest import SALES_CSV  # noqa: F401
from test_auth import auth_on  # noqa: F401
from test_transforms import CSV, ROWS, close, col, run, table, team, upload  # noqa: F401

LONG_CSV = (
    "sujeito,tempo,nota,grupo\n"
    "s1,pre,5,A\n"
    "s1,pos,8,A\n"
    "s2,pre,6,B\n"
    "s2,pos,,B\n"
    "s3,pos,9,A\n"
    "s3,pre,4,A\n"
)
LONG = [("s1", "pre", 5, "A"), ("s1", "pos", 8, "A"), ("s2", "pre", 6, "B"), ("s2", "pos", None, "B"), ("s3", "pos", 9, "A"), ("s3", "pre", 4, "A")]

NAMES_CSV = "id,nome,idade\n1,Ana,20\n2,Bia,21\n3,Caio,22\n9,Zeca,30\n"
DUP_CSV = "id,extra\n1,x\n1,y\n2,z\n"


@pytest.fixture
async def ds(client):
    return await upload(client)


# ---------- resumir ----------

async def test_summarize_matches_python_in_first_appearance_order(client, ds):
    aggs = [{"name": "n", "fn": "count_rows"}, {"name": "media", "fn": "mean", "column": "nota1"},
            {"name": "soma", "fn": "sum", "column": "nota3"}, {"name": "min", "fn": "min", "column": "nota1"},
            {"name": "max", "fn": "max", "column": "nota1"}, {"name": "med", "fn": "median", "column": "nota2"},
            {"name": "dp", "fn": "std", "column": "nota1"}, {"name": "cont", "fn": "count", "column": "nota1"},
            {"name": "dist", "fn": "count_distinct", "column": "data"}]
    rows, body = await table(client, ds, {"op": "summarize", "by": ["grupo"], "aggs": aggs})
    assert body["total_rows"] == 2 and col(rows, "grupo") == ["A", "B"]  # ordem de aparição
    for r in rows:
        mine = [x for x in ROWS if x["grupo"] == r["grupo"]]
        n1 = [x["nota1"] for x in mine if x["nota1"] is not None]
        n2 = [x["nota2"] for x in mine if x["nota2"] is not None]
        n3 = [x["nota3"] for x in mine if x["nota3"] is not None]
        assert r["n"] == len(mine) and r["cont"] == len(n1)
        assert abs(r["media"] - statistics.fmean(n1)) < 1e-9 and r["soma"] == sum(n3)
        assert r["min"] == min(n1) and r["max"] == max(n1) and abs(r["med"] - statistics.median(n2)) < 1e-9
        assert abs(r["dp"] - statistics.stdev(n1)) < 1e-9 and r["dist"] == len({x["data"] for x in mine})
    assert {c["name"]: c["dtype"] for c in body["columns"]}["soma"] == "BIGINT"  # soma de inteiros continua inteira


async def test_summarize_whole_table_and_two_keys(client, ds):
    rows, _ = await table(client, ds, {"op": "summarize", "by": [], "aggs": [{"name": "n", "fn": "count_rows"}, {"name": "m", "fn": "mean", "column": "nota2"}]})
    known = [x["nota2"] for x in ROWS if x["nota2"] is not None]
    assert len(rows) == 1 and rows[0]["n"] == 7 and abs(rows[0]["m"] - statistics.fmean(known)) < 1e-9
    rows, _ = await table(client, ds, {"op": "summarize", "by": ["grupo", "data"], "aggs": [{"name": "n", "fn": "count_rows"}]})
    ref = defaultdict(int)
    for x in ROWS:
        ref[(x["grupo"], x["data"])] += 1
    assert {(r["grupo"], r["data"]): r["n"] for r in rows} == dict(ref)
    assert [(r["grupo"], r["data"]) for r in rows][0] == ("A", "2024-01-15")


async def test_summarize_errors(client, ds):
    bad = lambda *a, by=("grupo",): run(client, ds, {"op": "summarize", "by": list(by), "aggs": list(a)})  # noqa: E731
    r = await bad({"name": "m", "fn": "mean", "column": "texto"})
    assert r.status_code == 422 and "não é numérica" in r.json()["detail"] and r.json()["detail"].startswith("Passo 1 (summarize)")
    assert "repetido" in (await bad({"name": "grupo", "fn": "count_rows"})).json()["detail"]
    assert "repetido" in (await bad({"name": "x", "fn": "count_rows"}, {"name": "X", "fn": "count_rows"})).json()["detail"]
    assert "não encontrada" in (await bad({"name": "m", "fn": "sum", "column": "nope"})).json()["detail"]
    assert "escolha a coluna" in (await bad({"name": "m", "fn": "sum"})).json()["detail"]
    assert (await run(client, ds, {"op": "summarize", "by": [], "aggs": []})).status_code == 422


# ---------- pivotar / despivotar ----------

@pytest.fixture
async def long(client):
    return await upload(client, LONG_CSV, "longo.csv")


async def test_pivot_wide_matches_python(client, long):
    rows, body = await table(client, long, {"op": "pivot", "index": ["sujeito"], "names_from": "tempo", "values": "nota", "fn": "first"})
    assert [c["name"] for c in body["columns"]] == ["sujeito", "pos", "pre"]  # novas colunas em ordem alfabética
    ref = defaultdict(dict)
    for s, t, n, _ in LONG:
        ref[s][t] = n
    assert col(rows, "sujeito") == ["s1", "s2", "s3"]  # ordem de aparição
    for r in rows:
        assert r["pre"] == ref[r["sujeito"]]["pre"] and r["pos"] == ref[r["sujeito"]]["pos"]
    assert [r for r in rows if r["sujeito"] == "s2"][0]["pos"] is None  # célula sem valor fica vazia


async def test_pivot_aggregates_and_prefix(client, long):
    rows, _ = await table(client, long, {"op": "pivot", "index": ["grupo"], "names_from": "tempo", "values": "nota", "fn": "sum", "prefix": "t_"})
    ref = defaultdict(lambda: defaultdict(list))
    for _, t, n, g in LONG:
        if n is not None:
            ref[g][t].append(n)
    for r in rows:
        for t in ("pre", "pos"):  # soma de nada é vazio, não 0 (como nas demais agregações)
            assert r[f"t_{t}"] == (sum(ref[r["grupo"]][t]) if ref[r["grupo"]][t] else None)
    rows, _ = await table(client, long, {"op": "pivot", "index": ["grupo"], "names_from": "tempo", "values": "nota", "fn": "mean"})
    for r in rows:
        assert abs(r["pre"] - statistics.fmean(ref[r["grupo"]]["pre"])) < 1e-9
    rows, _ = await table(client, long, {"op": "pivot", "index": ["grupo"], "names_from": "tempo", "values": "nota", "fn": "count"})
    assert {r["grupo"]: (r["pre"], r["pos"]) for r in rows} == {"A": (2, 2), "B": (1, 0)}


async def test_pivot_errors(client, long):
    p = lambda **kw: run(client, long, {"op": "pivot", "index": ["sujeito"], "names_from": "tempo", "values": "nota", **kw})  # noqa: E731
    assert "não é numérica" in (await p(values="grupo", fn="sum")).json()["detail"]
    assert "diferentes" in (await p(values="sujeito")).json()["detail"]
    r = await run(client, long, {"op": "pivot", "index": ["tempo"], "names_from": "sujeito", "values": "nota", "prefix": "", "fn": "first"})
    assert r.status_code == 200  # 3 sujeitos viram 3 colunas
    r = await run(client, long, {"op": "filter", "conditions": [{"column": "tempo", "operator": "eq", "value": "nada"}], "combine": "and"},
                  {"op": "pivot", "index": ["sujeito"], "names_from": "tempo", "values": "nota"})
    assert r.status_code == 422 and "não tem valores" in r.json()["detail"]


async def test_pivot_rejects_too_many_columns(client):
    csv = "id,k,v\n" + "\n".join(f"{i},k{i},{i}" for i in range(45))
    d = await upload(client, csv, "muitos.csv")
    r = await run(client, d, {"op": "pivot", "index": ["id"], "names_from": "k", "values": "v"})
    assert r.status_code == 422 and "mais de 40" in r.json()["detail"]


async def test_pivot_colliding_names(client):
    d = await upload(client, "id,k,v\n1,a,1\n1,A,2\n", "colide.csv")
    r = await run(client, d, {"op": "pivot", "index": ["id"], "names_from": "k", "values": "v"})
    assert r.status_code == 422 and "repetido" in r.json()["detail"]


async def test_unpivot_matches_python_and_keeps_row_order(client, ds):
    rows, body = await table(client, ds, {"op": "unpivot", "columns": ["nota1", "nota2", "nota3"], "names_to": "prova", "values_to": "nota"})
    assert [c["name"] for c in body["columns"]] == ["id", "grupo", "data", "texto", "prova", "nota"]
    ref = [(x["id"], p, x[p]) for x in ROWS for p in ("nota1", "nota2", "nota3")]  # linha por linha, coluna por coluna
    assert [(r["id"], r["prova"], r["nota"]) for r in rows] == ref and body["total_rows"] == 21
    rows, body = await table(client, ds, {"op": "unpivot", "columns": ["nota1", "nota2", "nota3"], "names_to": "prova", "values_to": "nota", "drop_nulls": True})
    assert [(r["id"], r["prova"], r["nota"]) for r in rows] == [t for t in ref if t[2] is not None]


async def test_unpivot_then_pivot_roundtrips(client, ds):
    rows, _ = await table(
        client, ds, {"op": "select", "columns": ["id", "nota1", "nota2"], "mode": "keep"},
        {"op": "dedupe", "columns": ["id"]},
        {"op": "unpivot", "columns": ["nota1", "nota2"], "names_to": "prova", "values_to": "nota"},
        {"op": "pivot", "index": ["id"], "names_from": "prova", "values": "nota", "fn": "first"})
    seen = {}
    for x in ROWS:
        seen.setdefault(x["id"], x)
    assert [(r["id"], r["nota1"], r["nota2"]) for r in rows] == [(i, x["nota1"], x["nota2"]) for i, x in seen.items()]


async def test_unpivot_errors(client, ds):
    u = lambda cols: run(client, ds, {"op": "unpivot", "columns": cols, "names_to": "a", "values_to": "b"})  # noqa: E731
    assert "tipos diferentes" in (await u(["nota1", "texto"])).json()["detail"]
    assert (await u(["nota1"])).status_code == 422
    assert "repetidas" in (await u(["nota1", "nota1"])).json()["detail"]
    r = await run(client, ds, {"op": "unpivot", "columns": ["nota1", "nota2"], "names_to": "id", "values_to": "b"})
    assert r.status_code == 422 and "repetido" in r.json()["detail"]


# ---------- mesclar ----------

@pytest.fixture
async def names(client):
    return await upload(client, NAMES_CSV, "nomes.csv")


def join(other, **kw):
    return {"op": "join", "other_id": other["id"], "kind": "left", "keys": [{"left": "id", "right": "id"}], **kw}


async def test_left_join_keeps_left_rows_in_order(client, ds, names):
    rows, body = await table(client, ds, join(names))
    assert [c["name"] for c in body["columns"]][-2:] == ["nome", "idade"] and body["total_rows"] == 7
    lookup = {1: ("Ana", 20), 2: ("Bia", 21), 3: ("Caio", 22)}
    assert [(r["id"], r["nome"], r["idade"]) for r in rows] == [(x["id"], *lookup.get(x["id"], (None, None))) for x in ROWS]


async def test_inner_full_and_anti_joins(client, ds, names):
    rows, _ = await table(client, ds, join(names, kind="inner"))
    assert col(rows, "id") == [x["id"] for x in ROWS if x["id"] in (1, 2, 3)]
    rows, body = await table(client, ds, join(names, kind="full"))
    assert body["total_rows"] == 8 and col(rows, "id")[-1] == 9 and rows[-1]["nome"] == "Zeca"  # só-da-direita no fim, chave preenchida
    assert rows[-1]["grupo"] is None
    rows, body = await table(client, ds, join(names, kind="anti"))
    assert col(rows, "id") == [x["id"] for x in ROWS if x["id"] not in (1, 2, 3)] and "nome" not in rows[0]


async def test_join_chooses_columns_suffix_and_different_key_names(client, ds):
    other = await upload(client, "codigo,grupo,valor\n1,X,100\n3,Y,300\n", "outro.csv")
    rows, body = await table(client, ds, {"op": "join", "other_id": other["id"], "kind": "left", "keys": [{"left": "id", "right": "codigo"}],
                                          "columns": ["grupo", "valor"], "suffix": "_ref"})
    assert [c["name"] for c in body["columns"]][-2:] == ["grupo_ref", "valor"]  # nome repetido ganha o sufixo
    assert [(r["grupo_ref"], r["valor"]) for r in rows][:3] == [("X", 100), (None, None), ("Y", 300)]


async def test_join_two_keys(client, ds):
    other = await upload(client, "id,grupo,peso\n1,A,10\n1,B,99\n3,B,30\n5,A,50\n", "dois.csv")
    rows, _ = await table(client, ds, {"op": "join", "other_id": other["id"], "kind": "left", "keys": [{"left": "id", "right": "id"}, {"left": "grupo", "right": "grupo"}]})
    ref = {(1, "A"): 10, (3, "B"): 30, (5, "A"): 50}
    assert col(rows, "peso") == [ref.get((x["id"], x["grupo"])) for x in ROWS]


async def test_join_refuses_repeated_keys_unless_allowed(client, ds):
    dup = await upload(client, DUP_CSV, "dup.csv")
    r = await run(client, ds, join(dup))
    assert r.status_code == 422 and "chave(s) repetida(s)" in r.json()["detail"]
    rows, body = await table(client, ds, join(dup, allow_multiple=True))
    assert body["total_rows"] == 8  # a linha id=1 aparece duas vezes
    assert [(r["id"], r["extra"]) for r in rows][:2] == [(1, "x"), (1, "y")]
    rows, body = await table(client, ds, join(dup, kind="anti"))  # exclusão não duplica: não exige chave única
    assert col(rows, "id") == [x["id"] for x in ROWS if x["id"] not in (1, 2)] and body["total_rows"] == 5


async def test_join_errors(client, ds, names):
    r = await run(client, ds, join(names, keys=[{"left": "texto", "right": "id"}]))
    assert r.status_code == 422 and "tipos diferentes" in r.json()["detail"]
    r = await run(client, ds, join(names, keys=[{"left": "nope", "right": "id"}]))
    assert "não encontrada" in r.json()["detail"]
    r = await run(client, ds, join({"id": "naoexiste"}))
    assert r.status_code == 422 and "não encontrado" in r.json()["detail"]
    r = await run(client, ds, join(names, columns=["idade", "idade"]))
    assert "repetidas" in r.json()["detail"]
    r = await run(client, ds, join(names), join(names))  # as colunas já existem; o sufixo evita o choque uma vez só
    assert r.status_code == 200


# ---------- acrescentar ----------

async def test_append_by_name_fills_missing_with_null(client, ds):
    other = await upload(client, "texto,id,extra\nnovo,10,e1\nvelho,11,e2\n", "mais.csv")
    rows, body = await table(client, ds, {"op": "append", "other_id": other["id"]})
    assert body["total_rows"] == 9
    assert [c["name"] for c in body["columns"]] == ["id", "grupo", "nota1", "nota2", "nota3", "data", "texto", "extra"]
    assert col(rows, "id") == [x["id"] for x in ROWS] + [10, 11]  # as linhas de cima ficam, as de fora vão ao fim
    assert col(rows, "texto")[-2:] == ["novo", "velho"] and col(rows, "grupo")[-2:] == [None, None] and col(rows, "extra")[:7] == [None] * 7


async def test_append_with_source_column(client, ds):
    other = await upload(client, "id,grupo\n10,C\n", "mais.csv")
    rows, _ = await table(client, ds, {"op": "append", "other_id": other["id"], "source_column": "origem", "label_current": "lote1", "label_other": "lote2"})
    assert col(rows, "origem") == ["lote1"] * 7 + ["lote2"]
    r = await run(client, ds, {"op": "append", "other_id": other["id"], "source_column": "origem", "label_current": "a", "label_other": "a"})
    assert "diferentes" in r.json()["detail"]
    r = await run(client, ds, {"op": "append", "other_id": other["id"], "source_column": "grupo", "label_current": "a", "label_other": "b"})
    assert "já existe" in r.json()["detail"]


async def test_append_errors(client, ds):
    r = await run(client, ds, {"op": "append", "other_id": (await upload(client, "zzz\n1\n", "z.csv"))["id"]})
    assert r.status_code == 422 and "nenhuma coluna em comum" in r.json()["detail"]
    r = await run(client, ds, {"op": "append", "other_id": (await upload(client, "id,grupo\nx,A\n", "t.csv"))["id"]})
    assert r.status_code == 422 and "converta o tipo" in r.json()["detail"]


# ---------- encadeamento, salvar e acesso ----------

async def test_summarize_then_join_then_save(client, ds, names):
    steps = [{"op": "dedupe", "columns": ["id"]}, {"op": "summarize", "by": ["id"], "aggs": [{"name": "m", "fn": "mean", "column": "nota1"}]}, join(names)]
    rows, body = await table(client, ds, *steps)
    assert body["total_rows"] == 6 and col(rows, "id") == [1, 2, 3, 4, 5, 6] and col(rows, "nome") == ["Ana", "Bia", "Caio", None, None, None]
    r = await client.post("/transforms/save", json={"recipe": {"source_id": ds["id"], "steps": steps}, "name": "resumo com nomes"})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["n_rows"] == 6 and [c["name"] for c in created["columns"]] == ["id", "m", "nome", "idade"]
    saved = (await client.get(f"/transforms/recipes/{created['id']}")).json()
    assert [s["op"] for s in saved["recipe"]["steps"]] == ["dedupe", "summarize", "join"]


# ---------- permissões: o outro dataset também respeita o acesso ----------

async def test_join_and_append_with_unreadable_dataset_are_refused_and_do_not_leak(team):
    c, ids = team
    open_ds = await upload(c["dona"], "id,v\n1,10\n2,20\n", "aberto.csv")
    secret = await upload(c["dona"], "id,salario\n1,9000\n2,8000\n", "secreto.csv")
    await c["dona"].put(f"/datasets/{secret['id']}/access", json={"restricted": True, "user_ids": [ids["outro"]], "rls": None})
    j = {"op": "join", "other_id": secret["id"], "kind": "left", "keys": [{"left": "id", "right": "id"}]}
    a = {"op": "append", "other_id": secret["id"]}
    for step in (j, a):
        r = await c["leitor"].post("/transforms/preview", json={"recipe": {"source_id": open_ds["id"], "steps": [step]}})
        assert r.status_code == 422 and "dataset não encontrado" in r.json()["detail"] and "salario" not in r.text  # não confirma que existe
    # quem pode ler os dois consegue; o derivado herda a restrição do dataset secreto, mesmo a origem sendo aberta
    saved = await c["outro"].post("/transforms/save", json={"recipe": {"source_id": open_ds["id"], "steps": [j]}, "name": "com salario"})
    assert saved.status_code == 201, saved.text
    assert saved.json()["restricted"] is True and "salario" in [col["name"] for col in saved.json()["columns"]]
    assert (await c["leitor"].get(f"/datasets/{saved.json()['id']}")).status_code == 404


async def test_join_uses_the_row_filtered_copy_of_the_other_dataset(team):
    c, ids = team
    d = await upload(c["dona"], "id,regiao,valor\n1,Sul,10\n2,Norte,20\n", "r.csv")
    await c["dona"].put(f"/datasets/{d['id']}/access", json={"restricted": False, "user_ids": [], "rls": {"column": "regiao", "attribute": "regiao"}})
    await c["admin"].patch(f"/users/{ids['outro']}", json={"attributes": {"regiao": "Sul"}})
    base = await upload(c["dona"], "id\n1\n2\n", "base.csv")
    step = {"op": "join", "other_id": d["id"], "kind": "left", "keys": [{"left": "id", "right": "id"}]}
    rec = {"source_id": base["id"], "steps": [step]}
    mine = (await c["outro"].post("/transforms/preview", json={"recipe": rec})).json()
    assert [r[2] for r in mine["rows"]] == [10, None]  # a linha do Norte não aparece para ele
    assert [r[2] for r in (await c["dona"].post("/transforms/preview", json={"recipe": rec})).json()["rows"]] == [10, 20]
