"""Passos por grupo e janela (8.3), conferidos contra cálculos independentes em Python."""
import statistics
from collections import defaultdict

import pytest
from conftest import SALES_CSV  # noqa: F401
from test_transforms import CSV, ROWS, close, col, run, table, upload  # noqa: F401


@pytest.fixture
async def ds(client):
    return await upload(client)


def groups(rows, key="grupo"):
    out = defaultdict(list)
    for i, r in enumerate(rows):
        out[r[key]].append(i)
    return out


def by_group(column, fn, by="grupo"):
    """Valor `fn` (sobre os não nulos) do grupo, repetido em cada linha."""
    result = [None] * len(ROWS)
    for idx in groups(ROWS, by).values():
        vals = [ROWS[i][column] for i in idx if ROWS[i][column] is not None]
        v = fn(vals) if vals else None
        for i in idx:
            result[i] = v
    return result


# ---------- por grupo ----------

@pytest.mark.parametrize("fn, ref", [
    ("mean", statistics.fmean), ("sum", sum), ("min", min), ("max", max), ("count", len), ("median", statistics.median),
    ("std", lambda v: statistics.stdev(v) if len(v) > 1 else None),
])
async def test_group_stat_matches_python_and_keeps_row_order(client, ds, fn, ref):
    rows, body = await table(client, ds, {"op": "group_stat", "name": "g", "fn": fn, "column": "nota1", "by": ["grupo"]})
    assert close(col(rows, "g"), by_group("nota1", ref)), fn
    assert col(rows, "id") == [r["id"] for r in ROWS]  # as linhas não mudam de lugar nem de quantidade
    assert body["total_rows"] == 7


async def test_group_stat_without_groups_is_whole_table_and_multi_key(client, ds):
    rows, _ = await table(client, ds, {"op": "group_stat", "name": "m", "fn": "mean", "column": "nota2", "by": []})
    known = [r["nota2"] for r in ROWS if r["nota2"] is not None]
    assert close(col(rows, "m"), [statistics.fmean(known)] * 7)
    rows, _ = await table(client, ds, {"op": "group_stat", "name": "n", "fn": "count", "column": "nota3", "by": ["grupo", "data"]})
    ref = defaultdict(int)
    for r in ROWS:
        ref[(r["grupo"], r["data"])] += r["nota3"] is not None
    assert col(rows, "n") == [ref[(r["grupo"], r["data"])] for r in ROWS]


async def test_integer_sum_stays_integer(client, ds):
    _, body = await table(client, ds, {"op": "group_stat", "name": "s", "fn": "sum", "column": "nota3", "by": ["grupo"]})
    assert {c["name"]: c["dtype"] for c in body["columns"]}["s"] == "BIGINT"  # não vira HUGEINT/DOUBLE no Parquet
    _, body = await table(client, ds, {"op": "row_stat", "name": "s", "fn": "sum", "columns": ["nota1", "nota2"]})
    assert {c["name"]: c["dtype"] for c in body["columns"]}["s"] == "BIGINT"


async def test_pct_total(client, ds):
    rows, _ = await table(client, ds, {"op": "pct_total", "name": "pct", "column": "nota3", "by": ["grupo"]})
    totals = by_group("nota3", sum)
    assert close(col(rows, "pct"), [None if r["nota3"] is None else 100 * r["nota3"] / t for r, t in zip(ROWS, totals)])
    for g in ("A", "B"):  # dentro de cada grupo os percentuais somam 100
        assert abs(sum(p for p, r in zip(col(rows, "pct"), ROWS) if r["grupo"] == g and p is not None) - 100) < 1e-9
    rows, _ = await table(client, ds, {"op": "pct_total", "name": "pct", "column": "nota3"})
    assert abs(sum(p for p in col(rows, "pct") if p is not None) - 100) < 1e-9  # sem grupo = % da tabela


async def test_zscore(client, ds):
    rows, _ = await table(client, ds, {"op": "zscore", "name": "z", "column": "nota1", "by": ["grupo"]})
    mean, sd = by_group("nota1", statistics.fmean), by_group("nota1", statistics.stdev)
    assert close(col(rows, "z"), [None if r["nota1"] is None else (r["nota1"] - m) / s for r, m, s in zip(ROWS, mean, sd)])
    # padronizado de verdade: média 0 e desvio 1 por grupo
    for g, idx in groups(ROWS).items():
        zs = [col(rows, "z")[i] for i in idx if col(rows, "z")[i] is not None]
        assert abs(statistics.fmean(zs)) < 1e-9 and abs(statistics.stdev(zs) - 1) < 1e-9


async def test_zscore_of_constant_group_is_null_not_error(client, ds):
    rows, _ = await table(client, ds, {"op": "filter", "conditions": [{"column": "id", "operator": "eq", "value": "3"}]},
                          {"op": "zscore", "name": "z", "column": "nota1", "by": ["grupo"]})
    assert col(rows, "z") == [None]  # grupo de 1 linha: desvio indefinido -> vazio


# ---------- ranking ----------

def ref_rank(method, desc=True):
    out = [None] * len(ROWS)
    for idx in groups(ROWS).values():
        vals = sorted({ROWS[i]["nota1"] for i in idx if ROWS[i]["nota1"] is not None}, reverse=desc)
        for i in idx:
            v = ROWS[i]["nota1"]
            if v is None:
                continue
            if method == "dense":
                out[i] = vals.index(v) + 1
            elif method == "rank":
                out[i] = 1 + sum((ROWS[j]["nota1"] > v if desc else ROWS[j]["nota1"] < v) for j in idx if ROWS[j]["nota1"] is not None)
        if method == "row":
            order = sorted((i for i in idx if ROWS[i]["nota1"] is not None), key=lambda i: (-ROWS[i]["nota1"] if desc else ROWS[i]["nota1"], i))
            for pos, i in enumerate(order, 1):
                out[i] = pos
    return out


@pytest.mark.parametrize("method", ["rank", "dense", "row"])
@pytest.mark.parametrize("desc", [True, False])
async def test_rank_methods(client, ds, method, desc):
    rows, _ = await table(client, ds, {"op": "rank", "name": "r", "column": "nota1", "by": ["grupo"], "desc": desc, "method": method})
    assert col(rows, "r") == ref_rank(method, desc), (method, desc)  # empate (6 e 6 no grupo A) e vazio (id 4) incluídos


# ---------- acumulado e média móvel ----------

def ref_running(column, fn, window=None, by="grupo", order="id", require_full=False):
    out = [None] * len(ROWS)
    for idx in groups(ROWS, by).values():
        ordered = sorted(idx, key=lambda i: (ROWS[i][order], i))  # desempate pela posição original, como o servidor
        for pos, i in enumerate(ordered):
            frame = ordered[max(0, pos - window + 1):pos + 1] if window else ordered[:pos + 1]
            vals = [ROWS[j][column] for j in frame if ROWS[j][column] is not None]
            if require_full and window and len(frame) < window:
                continue
            out[i] = (fn(vals) if vals else (0 if fn is len else None)) if fn is not None else None
    return out


@pytest.mark.parametrize("fn, ref", [("sum", sum), ("mean", statistics.fmean), ("min", min), ("max", max), ("count", len)])
async def test_cumulative(client, ds, fn, ref):
    rows, _ = await table(client, ds, {"op": "running", "name": "acc", "fn": fn, "column": "nota3", "by": ["grupo"], "order_by": [{"column": "id"}]})
    assert close(col(rows, "acc"), ref_running("nota3", ref)), fn
    assert col(rows, "id") == [r["id"] for r in ROWS]  # ordenar a janela não reordena a saída


@pytest.mark.parametrize("require_full", [False, True])
async def test_moving_average(client, ds, require_full):
    rows, _ = await table(client, ds, {"op": "running", "name": "mm", "fn": "mean", "column": "nota2", "window": 3, "by": ["grupo"],
                                       "order_by": [{"column": "id"}], "require_full": require_full})
    assert close(col(rows, "mm"), ref_running("nota2", statistics.fmean, 3, require_full=require_full))


async def test_running_without_order_uses_current_row_order(client, ds):
    rows, _ = await table(client, ds, {"op": "running", "name": "acc", "fn": "sum", "column": "nota3"})
    seen, expected = 0, []
    for r in ROWS:
        seen += r["nota3"] or 0
        expected.append(seen)
    assert col(rows, "acc") == expected


async def test_running_respects_a_previous_sort_step_and_descending_order(client, ds):
    rows, _ = await table(client, ds, {"op": "running", "name": "acc", "fn": "sum", "column": "nota3", "order_by": [{"column": "id", "desc": True}]})
    ordered = sorted(range(7), key=lambda i: (-ROWS[i]["id"], i))
    acc, any_seen, expected = 0, False, [None] * 7
    for i in ordered:
        if ROWS[i]["nota3"] is not None:
            acc, any_seen = acc + ROWS[i]["nota3"], True
        expected[i] = acc if any_seen else None  # soma de nada é vazio, não 0 (id 6 vem primeiro e tem nota3 vazia)
    assert col(rows, "acc") == expected and expected[5] is None


# ---------- diferença / variação ----------

def ref_lag(kind, periods=1):
    out = [None] * len(ROWS)
    for idx in groups(ROWS).values():
        ordered = sorted(idx, key=lambda i: (ROWS[i]["id"], i))
        for pos, i in enumerate(ordered):
            if pos < periods:
                continue
            prev, cur = ROWS[ordered[pos - periods]]["nota1"], ROWS[i]["nota1"]
            if kind == "previous":
                out[i] = prev
            elif cur is not None and prev is not None:
                out[i] = cur - prev if kind == "diff" else (None if prev == 0 else 100 * (cur - prev) / prev)
    return out


@pytest.mark.parametrize("kind", ["diff", "pct_change", "previous"])
@pytest.mark.parametrize("periods", [1, 2])
async def test_lag(client, ds, kind, periods):
    rows, _ = await table(client, ds, {"op": "lag", "name": "d", "column": "nota1", "kind": kind, "periods": periods, "by": ["grupo"], "order_by": [{"column": "id"}]})
    assert close(col(rows, "d"), ref_lag(kind, periods)), (kind, periods)


# ---------- encadeamento e erros ----------

async def test_group_mean_then_deviation_from_group_mean(client, ds):
    """Receita típica do Power BI: média do grupo e quanto cada linha se afasta dela."""
    rows, _ = await table(client, ds, {"op": "group_stat", "name": "media_grupo", "fn": "mean", "column": "nota1", "by": ["grupo"]},
                          {"op": "arith", "name": "desvio", "left": {"col": "nota1"}, "operator": "-", "right": {"col": "media_grupo"}})
    means = by_group("nota1", statistics.fmean)
    assert close(col(rows, "desvio"), [None if r["nota1"] is None else r["nota1"] - m for r, m in zip(ROWS, means)])


async def test_window_steps_after_dedupe_and_filter(client, ds):
    rows, _ = await table(client, ds, {"op": "dedupe"}, {"op": "filter", "conditions": [{"column": "grupo", "operator": "eq", "value": "A"}]},
                          {"op": "running", "name": "acc", "fn": "sum", "column": "nota3", "order_by": [{"column": "id"}]})
    assert col(rows, "id") == [1, 2, 5] and col(rows, "acc") == [9, 15, 23]


@pytest.mark.parametrize("step, fragment", [
    ({"op": "group_stat", "name": "g", "fn": "mean", "column": "grupo", "by": []}, "não é numérica"),
    ({"op": "group_stat", "name": "g", "fn": "count", "column": "grupo", "by": ["grupo"]}, None),
    ({"op": "group_stat", "name": "g", "fn": "mean", "column": "nota1", "by": ["nao_existe"]}, "coluna não encontrada"),
    ({"op": "group_stat", "name": "nota1", "fn": "mean", "column": "nota2", "by": []}, "já existe uma coluna"),
    ({"op": "pct_total", "name": "p", "column": "texto"}, "não é numérica"),
    ({"op": "zscore", "name": "z", "column": "grupo"}, "não é numérica"),
    ({"op": "running", "name": "r", "fn": "sum", "column": "nota1", "order_by": [{"column": "nao_existe"}]}, "coluna não encontrada"),
    ({"op": "lag", "name": "l", "column": "texto", "kind": "diff"}, "não é numérica"),
    ({"op": "lag", "name": "l", "column": "texto", "kind": "previous"}, None),  # valor anterior serve para texto
])
async def test_window_errors_and_text_exceptions(client, ds, step, fragment):
    r = await run(client, ds, step)
    if fragment is None:
        assert r.status_code == 200, r.text
    else:
        assert r.status_code == 422 and fragment in r.json()["detail"] and r.json()["detail"].startswith("Passo 1")


async def test_window_validation_limits(client, ds):
    assert (await run(client, ds, {"op": "running", "name": "r", "fn": "sum", "column": "nota1", "window": 1})).status_code == 422
    assert (await run(client, ds, {"op": "lag", "name": "l", "column": "nota1", "kind": "diff", "periods": 0})).status_code == 422
    assert (await run(client, ds, {"op": "group_stat", "name": "g", "fn": "median", "column": "nota1", "by": [f"c{i}" for i in range(11)]})).status_code == 422
    assert (await run(client, ds, {"op": "group_stat", "name": "g", "fn": "avg", "column": "nota1"})).status_code == 422


async def test_reserved_row_index_column_is_refused(client):
    d = await upload(client, "__rn,v\n1,2\n3,4\n", "r.csv")
    r = await run(client, d, {"op": "group_stat", "name": "g", "fn": "sum", "column": "v", "by": []})
    assert r.status_code == 422 and "reservada" in r.json()["detail"]


async def test_window_recipe_saves_as_dataset(client, ds):
    steps = [{"op": "group_stat", "name": "media_grupo", "fn": "mean", "column": "nota1", "by": ["grupo"]},
             {"op": "rank", "name": "pos", "column": "nota1", "by": ["grupo"]}]
    r = await client.post("/transforms/save", json={"recipe": {"source_id": ds["id"], "steps": steps}, "name": "com grupo"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["n_rows"] == 7 and {c["name"]: c["dtype"] for c in new["columns"]}["pos"] == "BIGINT"
    q = await client.post("/queries/run", json={"sql": f'SELECT id, media_grupo, pos FROM "{new["table_name"]}" ORDER BY id LIMIT 2'})
    assert q.json()["rows"][0][2] == 1  # id 1 (nota1 = 7) é o 1º do grupo A
