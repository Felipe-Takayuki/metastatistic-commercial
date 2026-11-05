"""Análises estatísticas ponta a ponta (API -> pool -> worker -> módulos JASP), conferidas contra o R puro.

Requer a pilha no ar:  docker compose up -d --build
Rodar:                 RUN_INTEGRATION=1 pytest tests/test_analyses_integration.py

Os valores de referência (tests/fixtures/r_reference.json) vêm de stats::aov / TukeyHSD / cor.test / lm / chisq.test sobre as
fixtures; make_reference.R os regenera. Dados sintéticos e determinísticos: nada de dados reais de experimento no repositório.
"""
import json
import math
import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

API = os.getenv("API_URL", "http://localhost:8000")
FIX = Path(__file__).parent / "fixtures"
REF = json.loads((FIX / "r_reference.json").read_text())
TOL = 1e-6


def close(got, want, rel=TOL):
    assert isinstance(got, (int, float)), f"valor não numérico: {got!r} (esperado {want!r})"
    assert math.isclose(got, want, rel_tol=rel, abs_tol=1e-9), f"JASP={got!r} R={want!r}"


def tables(node, path=""):
    out = {}
    if isinstance(node, dict):
        if isinstance(node.get("schema"), dict) and isinstance(node.get("data"), list):
            out[path] = node
        for k, v in node.items():
            if k not in ("schema", ".meta", "data", "footnotes"):
                out.update(tables(v, f"{path}/{k}"))
    return out


def table(result, suffix):
    found = [t for p, t in tables(result["results"]).items() if p.endswith(suffix)]
    assert len(found) == 1, f"esperava 1 tabela terminada em {suffix!r}, achei {len(found)}: {[p.split('/')[-1] for p in tables(result['results'])]}"
    return found[0]


def post_hoc_table(result, factor):
    found = [t for p, t in tables(result["results"]).items() if "postHocStandard" in p and factor in p.split("/")[-1]]
    assert len(found) == 1, f"post hoc de {factor!r}: {len(found)} tabelas"
    return found[0]


def run(analysis, dataset_id, options):
    r = httpx.post(f"{API}/analyses/run", json={"analysis": analysis, "dataset_id": dataset_id, "options": options}, timeout=180)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "complete", body["results"].get("errorMessage", body)[:300] if isinstance(body["results"], dict) else body
    return body


@pytest.fixture(scope="module")
def data():
    ids, created = {}, []

    def upload(name, path):
        r = httpx.post(f"{API}/datasets", files={"file": (name, path.read_bytes(), "text/csv")}, timeout=60)
        assert r.status_code == 201, r.text
        created.append(r.json()["id"])
        return r.json()

    def derive(name, sql):
        r = httpx.post(f"{API}/datasets/from-query", json={"name": name, "sql": sql}, timeout=60)
        assert r.status_code == 201, r.text
        created.append(r.json()["id"])
        return r.json()

    raw = upload("e2e-dbc-raw.csv", FIX / "dbc_raw.csv")
    # O bloco é derivado pela posição da linha (1,2,3,4,1,2,3,4…): exatamente o fluxo "Salvar consulta como dataset".
    dbc = derive("e2e-dbc", f'SELECT ((row_number() OVER () - 1) % 4) + 1 AS bloco, * FROM "{raw["table_name"]}"')
    ids["dbc"] = dbc["id"]
    ids["fatorial"] = upload("e2e-fatorial.csv", FIX / "fatorial.csv")["id"]
    src = upload("e2e-faixa-src.csv", FIX / "ttest.csv")
    faixas = derive("e2e-faixas", f'SELECT "group" AS grupo, CASE WHEN score < 9 THEN \'baixo\' WHEN score < 11 THEN \'medio\' ELSE \'alto\' END AS faixa FROM "{src["table_name"]}"')
    ids["faixas"] = faixas["id"]
    ids["dbc_meta"] = dbc
    yield ids
    for i in created:
        httpx.delete(f"{API}/datasets/{i}")


def anova_opts(factors, terms, **extra):
    return {"dependent": "produtividade", "fixedFactors": factors, "modelTerms": [{"components": t} for t in terms],
            "descriptives": True, "postHocCorrectionTukey": True, "postHocTerms": [], "effectSizeEstimates": False, **extra}


def test_derived_block_column_has_the_right_type(data):
    cols = {c["name"]: c for c in data["dbc_meta"]["columns"]}
    assert list(cols)[0] == "bloco" and cols["bloco"]["measurement"] == "ordinal" and cols["bloco"]["n_distinct"] == 4
    assert cols["tratamento"]["measurement"] == "ordinal" and cols["tratamento"]["n_distinct"] == 8


def test_anova_randomized_block_design_matches_R(data):
    res = run("Anova", data["dbc"], anova_opts(["tratamento", "bloco"], [["tratamento"], ["bloco"]]))
    rows = {r["cases"]: r for r in table(res, "anovaTable")["data"]}
    assert set(rows) == {"tratamento", "bloco", "Residuals"}  # modelo ADITIVO: sem linha de interação
    for key, name in (("trat", "tratamento"), ("bloco", "bloco")):
        close(rows[name]["Df"], REF["anova"][key]["df"]); close(rows[name]["F value"], REF["anova"][key]["F"]); close(rows[name]["Pr(>F)"], REF["anova"][key]["p"])
    assert rows["Residuals"]["Df"] == REF["anova"]["resid"]["df"] == 21  # 32 - 1 - 7 - 3 (com a interação seria 0)
    close(rows["Residuals"]["Mean Sq"], REF["anova"]["resid"]["ms"]); close(rows["Residuals"]["Sum Sq"], REF["anova"]["resid"]["ss"])


def test_anova_tukey_post_hoc_matches_R_for_all_28_pairs(data):
    res = run("Anova", data["dbc"], anova_opts(["tratamento", "bloco"], [["tratamento"], ["bloco"]], postHocTerms=["tratamento"]))
    ph = post_hoc_table(res, "tratamento")
    got = {(str(r["contrast_A"]), str(r["contrast_B"])): r for r in ph["data"]}
    assert len(got) == len(REF["tukey"]) == 28
    for ref in REF["tukey"]:
        row = got[(str(ref["a"]), str(ref["b"]))]
        close(row["estimate"], ref["diff"]); close(row["tukey"], ref["p"], 1e-5)


def test_anova_additive_model_on_a_replicated_design_has_no_interaction_row(data):
    """O bug original: o JASP acrescentava A:B ao pedir só A e B (o QML repovoa o modelo). O remendo deve devolver o aditivo."""
    res = run("Anova", data["fatorial"], {"dependent": "y", "fixedFactors": ["A", "B"], "modelTerms": [{"components": ["A"]}, {"components": ["B"]}],
                                          "descriptives": False, "postHocTerms": [], "effectSizeEstimates": False})
    rows = {r["cases"]: r for r in table(res, "anovaTable")["data"]}
    assert set(rows) == {"A", "B", "Residuals"}, f"linhas: {list(rows)}"
    ref = REF["fatorial_add"]
    for k in ("A", "B"):
        close(rows[k]["Df"], ref[k]["df"]); close(rows[k]["F value"], ref[k]["F"]); close(rows[k]["Pr(>F)"], ref[k]["p"])
    assert rows["Residuals"]["Df"] == ref["resid"]["df"] == 20


def test_anova_with_interaction_matches_R(data):
    res = run("Anova", data["fatorial"], {"dependent": "y", "fixedFactors": ["A", "B"],
                                          "modelTerms": [{"components": ["A"]}, {"components": ["B"]}, {"components": ["A", "B"]}],
                                          "descriptives": False, "postHocTerms": [], "effectSizeEstimates": False})
    rows = {r["cases"]: r for r in table(res, "anovaTable")["data"]}
    inter = next(k for k in rows if "✻" in k)  # o JASP rotula a interação como "A ✻ B"
    ref = REF["fatorial"]
    close(rows[inter]["Df"], ref["AB"]["df"]); close(rows[inter]["F value"], ref["AB"]["F"]); close(rows[inter]["Pr(>F)"], ref["AB"]["p"])
    close(rows["A"]["F value"], ref["A"]["F"]); close(rows["B"]["F value"], ref["B"]["F"])
    assert rows["Residuals"]["Df"] == ref["resid"]["df"] == 18


def test_correlation_pearson_and_spearman_match_R(data):
    res = run("Correlation", data["dbc"], {"variables": ["produtividade", "altura", "diametro"], "pearson": True, "spearman": True, "kendallsTauB": False,
                                           "pairwiseDisplay": True, "sampleSize": True, "ci": True, "ciLevel": 0.95, "alternative": "twoSided"})
    rows = {(r["variable1"], r["variable2"]): r for r in table(res, "mainTable")["data"]}
    assert len(rows) == 3
    for c in REF["corr"]:
        r = rows[(c["v1"], c["v2"])]
        assert r["sample.size"] == c["n"]
        close(r["pearson_estimate"], c["pearson"]); close(r["pearson_p.value"], c["p_pearson"])
        close(r["pearson_lower.ci"], c["lo"], 1e-5); close(r["pearson_upper.ci"], c["hi"], 1e-5)
        close(r["spearman_estimate"], c["spearman"]); close(r["spearman_p.value"], c["p_spearman"], 1e-5)


def test_linear_regression_is_one_model_with_all_predictors_and_matches_R(data):
    res = run("RegressionLinear", data["dbc"], {"dependent": "produtividade", "covariates": ["altura", "diametro"], "factors": [], "modelFit": True,
                                               "coefficientEstimate": True, "coefficientCi": True, "coefficientCiLevel": 0.95,
                                               "modelTerms": [{"components": ["altura", "diametro"], "name": "model1", "title": "Model 1"}]})
    summary = table(res, "summaryTable")["data"]
    assert len(summary) == 1, "deve ser UM modelo com os dois preditores (e não um modelo por preditor)"
    ref = REF["reg"]
    close(summary[0]["R2"], ref["R2"]); close(summary[0]["adjR2"], ref["adjR2"]); close(summary[0]["RMSE"], ref["sigma"])
    an = {r["cases"]: r for r in table(res, "anovaTable")["data"]}
    close(an["Regression"]["F"], ref["F"]); close(an["Regression"]["p"], ref["p"]); assert an["Residual"]["df"] == ref["df_res"]
    coefs = table(res, "coeffTable")["data"]
    assert [c["name"] for c in coefs] == ["(Intercept)", "altura", "diametro"]
    for row, want in zip(coefs, ref["coef"]):
        for k, rk in (("unstandCoeff", "est"), ("SE", "se"), ("t", "t"), ("p", "p"), ("lower", "lo"), ("upper", "hi")):
            close(row[k], want[rk])


def test_chi_square_matches_R(data):
    res = run("ContingencyTables", data["faixas"], {"rows": ["grupo"], "columns": ["faixa"], "chiSquared": True, "chiSquaredContinuityCorrection": False,
                                                  "likelihoodRatio": True, "phiAndCramersV": True, "countsExpected": True})
    ref = REF["chi"]
    cr = table(res, "crossTabChisq")["data"][0]
    close(cr["value[chiSquared]"], ref["X2"]); assert cr["df[chiSquared]"] == ref["df"]; close(cr["p[chiSquared]"], ref["p"])
    close(cr["value[likelihood]"], ref["G2"]); close(cr["p[likelihood]"], ref["p_g2"]); assert cr["value[N]"] == ref["n"]
    close(table(res, "crossTabNominal")["data"][0]["value[CramerV]"], ref["V"])
    expected = [r for r in table(res, "crossTabMain")["data"] if r["grupo"] != "Total"]
    got = [row[f"{lvl}[expected]"] for lvl in ref["levels"] for row in expected]  # R: colunas por nível, linhas por grupo
    for g, w in zip(got, ref["expected"]):
        close(g, w)


def test_unknown_option_and_forbidden_analysis_are_rejected_for_the_new_analyses(data):
    for analysis in ("Anova", "Correlation", "RegressionLinear", "ContingencyTables"):
        r = httpx.post(f"{API}/analyses/run", json={"analysis": analysis, "dataset_id": data["dbc"], "options": {"opcaoQueNaoExiste": True}}, timeout=60)
        assert r.status_code == 422 and "opcaoQueNaoExiste" in r.json()["detail"], (analysis, r.text[:200])
    assert httpx.post(f"{API}/analyses/run", json={"analysis": "Manova", "dataset_id": data["dbc"], "options": {}}, timeout=60).status_code == 422


def test_endurance_many_distinct_concurrent_analyses_never_hang(data):
    """Guarda contra o travamento intermitente do motor (análise > 60 s -> 504 -> reinício de ~50 s).
    48 análises distintas, 6 em paralelo (os dois workers + fila), de tipos variados: nenhuma pode falhar nem passar de 30 s."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    def anova(i):
        flags = dict(descriptives=bool(i & 1), qqPlot=bool(i & 4), effectSizeEstimates=bool(i & 8), effectSizeEtaSquared=bool(i & 8))
        if i & 2:   # Levene exige repetições: só no fatorial (no bloco casualizado, 1 observação por célula, o JASP recusa)
            o = {**anova_opts(["A", "B"], [["A"], ["B"]], homogeneityTests=True, **flags), "dependent": "y"}
            if i & 16:
                o["postHocTerms"] = ["A"]
            return ("Anova", data["fatorial"], o)
        o = anova_opts(["tratamento", "bloco"], [["tratamento"], ["bloco"]], **flags)
        if i & 16:
            o["postHocTerms"] = ["tratamento"]
        return ("Anova", data["dbc"], o)

    corr = ("Correlation", data["dbc"], {"variables": ["produtividade", "altura", "diametro"], "pearson": True, "spearman": True, "ci": True})
    reg = ("RegressionLinear", data["dbc"], {"dependent": "produtividade", "covariates": ["altura", "diametro"], "factors": [], "modelFit": True,
                                             "coefficientEstimate": True, "modelTerms": [{"components": ["altura", "diametro"], "name": "model1", "title": "Model 1"}]})
    chi = ("ContingencyTables", data["faixas"], {"rows": ["grupo"], "columns": ["faixa"], "chiSquared": True})
    jobs = [anova(i) for i in range(32)] + [corr, reg, chi] * 5 + [anova(i) for i in (3, 9, 21)]   # 32 + 15 + 3 = 50

    def one(job):
        t = time.time()
        run(*job)
        return time.time() - t

    with ThreadPoolExecutor(6) as ex:
        times = list(ex.map(one, jobs))
    assert len(times) >= 48 and max(times) < 30, f"mais lenta: {max(times):.1f}s"

