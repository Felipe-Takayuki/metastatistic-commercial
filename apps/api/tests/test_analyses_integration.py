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
    ids["nivel"] = derive("e2e-nivel", f"SELECT CASE WHEN produtividade >= 196 THEN 'alto' ELSE 'baixo' END AS nivel, * FROM \"{raw['table_name']}\"")["id"]
    ids["fatorial"] = upload("e2e-fatorial.csv", FIX / "fatorial.csv")["id"]
    ids["pres"] = upload("e2e-pressupostos.csv", FIX / "pressupostos.csv")["id"]
    tt = upload("e2e-ttest.csv", FIX / "ttest.csv")
    ids["tt"] = tt["id"]
    ids["colin"] = derive("e2e-colinear", f"SELECT produtividade, altura, 2 * altura + (CAST(FLOOR(produtividade) AS BIGINT) % 3) AS altura2, diametro FROM \"{raw['table_name']}\"")["id"]
    ids["steps"] = derive("e2e-passos", f"SELECT CASE WHEN altura + 5 * ((CAST(FLOOR(produtividade) AS BIGINT) % 7) - 3) >= 140 THEN 'alto' ELSE 'baixo' END AS nivel, "
                                       f"altura, diametro, 2 * altura + (CAST(FLOOR(produtividade) AS BIGINT) % 3) AS altura2 FROM \"{raw['table_name']}\"")["id"]
    ids["rm2"] = upload("e2e-rm2.csv", FIX / "rm2.csv")["id"]
    ids["resp"] = derive("e2e-resposta", f"SELECT \"group\" AS grupo, score, CASE WHEN score >= 10.5 THEN 'sim' ELSE 'nao' END AS resposta FROM \"{tt['table_name']}\"")["id"]
    ids["rm"] = upload("e2e-medidas-repetidas.csv", FIX / "medidas_repetidas.csv")["id"]
    fr = upload("e2e-friedman.csv", FIX / "friedman.csv")
    ids["friedman"] = fr["id"]
    # Likert: c1 é ORDINAL (inteiros, 8 valores distintos); c2/c3 são escalares; grupo/nivel derivados por SQL
    ids["lik"] = derive("e2e-likert", f"SELECT CASE WHEN CAST(substr(sujeito, 2) AS INTEGER) % 2 = 0 THEN 'a' ELSE 'b' END AS grupo, "
                                      f"CASE WHEN c3 >= 16 THEN 'alto' ELSE 'baixo' END AS nivel, * FROM \"{fr['table_name']}\"")["id"]
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


def cell(v):
    """Células com formato próprio chegam como {value, type, format}."""
    return v["value"] if isinstance(v, dict) else v


def test_paired_t_test_matches_R(data):
    ref = REF["paired"]
    res = run("TTestPairedSamples", data["dbc"], {"pairs": [["altura", "diametro"]], "student": True, "wilcoxon": True, "descriptives": True,
                                                  "meanDifference": True, "meanDifferenceCi": True, "effectSize": True})
    rows = {r["test"]: r for r in table(res, "ttest")["data"]}
    st = rows["Student"]
    close(st["Statistic"], ref["t"]); assert st["df"] == ref["df"]; close(st["p"], ref["p"]); close(st["md"], ref["mean_diff"])
    close(st["lowerCIlocationParameter"], ref["lo"]); close(st["upperCIlocationParameter"], ref["hi"]); close(st["d"], ref["d"])
    close(rows["Wilcoxon"]["p"], ref["wilcoxon_p"])  # p exato, como o R sem empates e n < 50
    assert st["v1"] == "altura" and st["v2"] == "diametro"
    d = {r["v"]: r for r in table(res, "ttestDescriptives_table")["data"]}
    assert d["altura"]["N"] == d["diametro"]["N"] == ref["n"]


def test_paired_t_test_one_sided_matches_R(data):
    res = run("TTestPairedSamples", data["dbc"], {"pairs": [["altura", "diametro"]], "student": True, "alternative": "greater"})
    close(table(res, "ttest")["data"][0]["p"], REF["paired"]["p_greater"])


def test_one_sample_t_test_matches_R(data):
    ref = REF["onesample"]
    opts = {"dependent": ["produtividade"], "testValue": 200, "student": True, "wilcoxon": True, "descriptives": True,
            "meanDifference": True, "meanDifferenceCi": True, "effectSize": True}
    res = run("TTestOneSample", data["dbc"], opts)
    rows = {r["test"]: r for r in table(res, "ttest")["data"]}
    st = rows["Student"]
    close(st["Statistic"], ref["t"]); assert st["df"] == ref["df"]; close(st["p"], ref["p"])
    # o JASP reporta a DIFERENÇA em relação ao valor de referência (e o IC dela); o R, a média e o IC da média
    close(st["lowerCIlocationParameter"], ref["lo"] - 200); close(st["upperCIlocationParameter"], ref["hi"] - 200); close(st["d"], ref["d"])
    close(st["m"], ref["mean"] - 200)
    close(rows["Wilcoxon"]["p"], ref["wilcoxon_p"])
    close(table(run("TTestOneSample", data["dbc"], {**opts, "alternative": "greater", "wilcoxon": False}), "ttest")["data"][0]["p"], ref["p_greater"])


def test_descriptives_match_R(data):
    ref = REF["desc"]
    res = run("Descriptives", data["dbc"], {"variables": ["produtividade"], "splitBy": [], "valid": True, "missing": True, "meanArithmetic": True, "median": True,
                                            "sd": True, "variance": True, "seMean": True, "minimum": True, "maximum": True, "range": True, "sum": True})
    row = table(res, "stats")["data"][0]
    assert row["Valid"] == ref["n"] and row["Missing"] == 0
    close(row["MeanArithmetic"], ref["mean"]); close(row["Std. Deviation"], ref["sd"]); close(row["Variance"], ref["variance"])
    close(row["Std. Error of Mean"], ref["se"]); close(row["Sum"], ref["sum"]); close(row["Range"], ref["range"])
    close(cell(row["Median"]), ref["median"]); close(cell(row["Minimum"]), ref["min"]); close(cell(row["Maximum"]), ref["max"])


def test_descriptives_split_by_a_factor(data):
    res = run("Descriptives", data["dbc"], {"variables": ["produtividade"], "splitBy": ["bloco"], "valid": True, "meanArithmetic": True, "sd": True})
    rows = table(res, "stats")["data"]
    assert [r["Level"] for r in rows] == ["1", "2", "3", "4"] and all(r["Valid"] == 8 for r in rows)  # 32 linhas / 4 blocos


def anova_rows(res):
    return {r["cases"]: r for r in table(res, "anovaTable")["data"]}


def test_ancova_blocks_with_covariate_is_additive_and_matches_R(data):
    """Fator + bloco + covariável, sem interações (o remendo do modelTerms vale para a Ancova também)."""
    ref = REF["ancova_blocks"]
    res = run("Ancova", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento", "bloco"], "covariates": ["altura"],
                                      "modelTerms": [{"components": ["tratamento"]}, {"components": ["bloco"]}, {"components": ["altura"]}]})
    rows = anova_rows(res)
    assert set(rows) == {"tratamento", "bloco", "altura", "Residuals"}, list(rows)
    for name, i in (("tratamento", 0), ("bloco", 1), ("altura", 2)):
        assert rows[name]["Df"] == ref["df"][i]
        close(rows[name]["Sum Sq"], ref["ss"][i]); close(rows[name]["F value"], ref["F"][i]); close(rows[name]["Pr(>F)"], ref["p"][i])
    assert rows["Residuals"]["Df"] == ref["resid_df"] == 20
    close(rows["Residuals"]["Sum Sq"], ref["resid_ss"])


def test_ancova_one_factor_with_covariate_matches_R(data):
    ref = REF["ancova_simple"]
    res = run("Ancova", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento"], "covariates": ["altura"],
                                      "modelTerms": [{"components": ["tratamento"]}, {"components": ["altura"]}]})
    rows = anova_rows(res)
    for name, i in (("tratamento", 0), ("altura", 1)):
        assert rows[name]["Df"] == ref["df"][i]; close(rows[name]["F value"], ref["F"][i]); close(rows[name]["Pr(>F)"], ref["p"][i])
    assert rows["Residuals"]["Df"] == ref["resid_df"]


def test_logistic_regression_matches_R(data):
    ref = REF["logit"]
    res = run("RegressionLogistic", data["nivel"], {
        "dependent": "nivel", "covariates": ["altura", "diametro"], "factors": [], "coefficientEstimate": True, "oddsRatio": True, "coefficientCi": True,
        "coefficientCiAsOddsRatio": True, "confusionMatrix": True, "accuracy": True, "auc": True,
        "modelTerms": [{"components": ["altura", "diametro"], "name": "model1", "title": "Model 1"}]})
    est = {r["param"]: r for r in table(res, "estimatesTable")["data"]}
    assert list(est) == ref["coefs"]
    import math
    for i, name in enumerate(ref["coefs"]):
        r = est[name]
        close(r["est"], ref["est"][i]); close(r["se"], ref["se"][i]); close(r["zval"], ref["z"][i]); close(r["pval"], ref["p"][i]); close(r["or"], ref["or"][i])
        close(r["cilo"], math.exp(ref["lo_wald"][i])); close(r["ciup"], math.exp(ref["hi_wald"][i]))  # IC de Wald, na escala da razão de chances
    summ = table(res, "modelSummary")["data"][0]
    close(summ["dev"], ref["deviance"]); close(summ["aic"], ref["aic"]); close(summ["bic"], ref["bic"]); assert summ["dof"] == ref["df_resid"]
    metrics = {r["met"]: r["val"] for r in table(res, "perfDiag_performanceMetrics")["data"]}
    close(metrics["Accuracy"], ref["accuracy"]); close(metrics["AUC"], ref["auc"])
    cm = {r["obs"]: r for r in table(res, "perfDiag_confusionMatrix")["data"]}
    assert (cm["alto"]["pred0"], cm["alto"]["pred1"]) == (ref["obs_alto_pred_alto"], ref["obs_alto_pred_baixo"])
    assert (cm["baixo"]["pred0"], cm["baixo"]["pred1"]) == (ref["obs_baixo_pred_alto"], ref["obs_baixo_pred_baixo"])


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



def test_kruskal_wallis_and_dunn_match_R(data):
    """Kruskal-Wallis é opção da Anova (`kruskalWallisFactors`); o Dunn do JASP usa a correção de empates (conferido na fórmula em R)."""
    ref = REF["kruskal"]
    res = run("Anova", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento"], "modelTerms": [{"components": ["tratamento"]}],
                                     "kruskalWallisFactors": ["tratamento"], "kruskalEffectSizeEstimates": True, "kruskalEpsilon": True, "kruskalEta": True, "postHocTypeDunn": True})
    row = table(res, "kruskalTable")["data"][0]
    assert row["factor"] == "tratamento" and row["df"] == ref["df"]
    close(row["statistic"], ref["H"]); close(row["p"], ref["p"]); close(row["epsiSqr"], ref["epsilon"]); close(row["etaSqr"], ref["eta"])
    dunn = {r["contrast"]: r for r in table(res, "dunnContainer_tratamento")["data"]}
    assert len(dunn) == len(ref["dunn"]) == 28
    for want in ref["dunn"]:
        got = dunn[want["contrast"]]
        close(got["z"], want["z"]); close(got["pval"], want["p"]); close(got["bonferroni"], want["bonferroni"]); close(got["holm"], want["holm"])


def test_kruskal_wallis_is_off_unless_asked(data):
    res = run("Anova", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento"], "modelTerms": [{"components": ["tratamento"]}],
                                     "kruskalWallisFactors": [], "postHocTypeDunn": False})
    assert not [p for p in tables(res["results"]) if "kruskal" in p.lower()]


def test_descriptives_frequency_table_matches_R(data):
    ref = REF["freq"]
    res = run("Descriptives", data["nivel"], {"variables": ["nivel"], "splitBy": [], "valid": True, "frequencyTables": True})
    all_rows = table(res, "tables_nivel")["data"]
    assert [r["Level"] for r in all_rows[-2:]] == ["Missing", "Total"]   # o JASP fecha a tabela com ausentes e total
    rows = all_rows[:-2]
    assert [r["Level"] for r in rows] == ref["levels"]
    assert all_rows[-2]["Frequency"] == 0 and all_rows[-1]["Frequency"] == sum(ref["n"])
    for r, n, pc, cu in zip(rows, ref["n"], ref["percent"], ref["cumulative"]):
        assert r["Frequency"] == n
        close(r["Percent"], pc); close(r["Valid Percent"], pc); close(r["Cumulative Percent"], cu)


def test_assumption_checks_match_R(data):
    """Os números por trás dos avisos automáticos (lib/assumptions.ts): Shapiro nos RESÍDUOS e Levene centrado na MEDIANA no t independente; na ANOVA, Levene centrado na MÉDIA."""
    ref = REF["pressupostos"]
    t = run("TTestIndependentSamples", data["pres"], {"dependent": ["y"], "group": "grupo", "student": True, "normalityTest": True, "equalityOfVariancesTest": True})
    sw = table(t, "ttestNormalTable")["data"][0]
    close(sw["W"], ref["shapiro_resid"]["W"]); close(sw["p"], ref["shapiro_resid"]["p"])
    lv = table(t, "equalityVariance")["data"][0]
    close(lv["fStat"], ref["levene_median"]["F"]); close(lv["p"], ref["levene_median"]["p"])
    a = run("Anova", data["pres"], {"dependent": "y", "fixedFactors": ["grupo"], "modelTerms": [{"components": ["grupo"]}], "homogeneityTests": True})
    lv = table(a, "leveneTable")["data"][0]
    close(lv["F"], ref["levene_mean"]["F"]); close(lv["p"], ref["levene_mean"]["p"])
    assert (lv["df1"], lv["df2"]) == (ref["levene_mean"]["df1"], ref["levene_mean"]["df2"])


def test_bayesian_ttests_match_BayesFactor(data):
    """Fator de Bayes (BF10, prior de Cauchy 0,707) do JASP = ttestBF do pacote BayesFactor."""
    ref = REF["bayes"]
    ind = run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group"})
    close(table(ind, "ttestTable")["data"][0]["BF"], ref["indep"], rel=1e-4)
    one = run("TTestBayesianOneSample", data["dbc"], {"dependent": ["produtividade"], "testValue": 200})
    close(table(one, "ttestTable")["data"][0]["BF"], ref["one"], rel=1e-4)
    # unilateral: "greater" = média > valor de referência = o intervalo (0, +inf) do BayesFactor
    gt = run("TTestBayesianOneSample", data["dbc"], {"dependent": ["produtividade"], "testValue": 200, "alternative": "greater"})
    close(table(gt, "ttestTable")["data"][0]["BF"], ref["one_nullint"][0], rel=1e-3)
    pr = run("TTestBayesianPairedSamples", data["dbc"], {"pairs": [["altura", "diametro"]]})
    close(table(pr, "ttestTable")["data"][0]["BF"], ref["paired"], rel=1e-4)


def test_bayes_factor_type_bf01_is_the_reciprocal(data):
    bf10 = table(run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group"}), "ttestTable")["data"][0]["BF"]
    bf01 = table(run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group", "bayesFactorType": "BF01"}), "ttestTable")["data"][0]["BF"]
    close(bf01, 1 / bf10, rel=1e-6)
    log = table(run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group", "bayesFactorType": "LogBF10"}), "ttestTable")["data"][0]["BF"]
    close(log, math.log(bf10), rel=1e-6)


def test_bayesian_anova_additive_model_matches_BayesFactor(data):
    """Modelo aditivo (tratamento + bloco): sem o remendo do modelTerms o JASP acrescentaria a interação (5 modelos em vez de 4)."""
    ref = REF["bayes"]["anova"]
    res = run("AnovaBayesian", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento", "bloco"], "setSeed": True, "seed": 1,
                                            "modelTerms": [{"components": ["tratamento"]}, {"components": ["bloco"]}]})
    rows = {r["Models"]: r for r in table(res, "tableModelComparison")["data"]}
    assert set(rows) == {"Null model", "tratamento", "bloco", "tratamento + bloco"}, list(rows)
    null = rows["Null model"]["BF10"]   # o JASP ordena por BF10 relativo ao melhor modelo; a referência do R é relativa ao nulo
    for name, want in zip(ref["models"], ref["bf"]):
        if name in rows:
            close(rows[name]["BF10"] / null, want, rel=0.03)   # Monte Carlo: erro de ~0,3% no JASP e ~1% no BayesFactor


def _images(node):
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == "data" and isinstance(v, str) and v.startswith("data:image/")] + [i for v in node.values() for i in _images(v)]
    if isinstance(node, list):
        return [i for v in node for i in _images(v)]
    return []


def test_bayesian_plots_come_back_as_embedded_images(data):
    res = run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group", "priorAndPosteriorPlot": True, "bfRobustnessPlot": True})
    assert len(_images(res["results"])) == 2
    assert not _images(run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group"})["results"])


def test_one_sample_z_test_matches_R(data):
    """Teste z de uma amostra (σ conhecido) é opção do TTestOneSample: Z = (média − μ0)/(σ/√n); d = diferença/σ; IC normal da diferença."""
    ref = REF["ztest"]
    opts = {"dependent": ["produtividade"], "testValue": 200, "student": False, "zTest": True, "zTestSd": ref["sd"], "meanDifference": True, "meanDifferenceCi": True, "effectSize": True}
    row = table(run("TTestOneSample", data["dbc"], opts), "ttest")["data"][0]
    close(row["Z"], ref["z"]); close(row["p"], ref["p"]); close(row["m"], ref["diff"])
    close(row["lowerCIlocationParameter"], ref["lo"]); close(row["upperCIlocationParameter"], ref["hi"]); close(row["d"], ref["d"])
    gt = table(run("TTestOneSample", data["dbc"], {**opts, "alternative": "greater"}), "ttest")["data"][0]
    close(gt["p"], ref["p_greater"])
    # junto com o Student: uma linha por teste
    both = {r["test"]: r for r in table(run("TTestOneSample", data["dbc"], {**opts, "student": True}), "ttest")["data"]}
    assert set(both) == {"Student", "Z"}
    close(both["Z"]["Statistic"], ref["z"])


RM_BASE = {"repeatedMeasuresFactors": [{"name": "tempo", "levels": ["t1", "t2", "t3"]}], "repeatedMeasuresCells": ["t1", "t2", "t3"],
           "withinModelTerms": [{"components": ["tempo"]}], "sphericityTests": True,
           "sphericityCorrectionNone": True, "sphericityCorrectionGreenhouseGeisser": True, "sphericityCorrectionHuynhFeldt": True}


def rm_within(res):
    return {(r["case"], r["correction"]): r for r in table(res, "withinAnovaTable")["data"]}


def test_repeated_measures_anova_one_within_factor_matches_R(data):
    """Um fator intra-sujeito (3 tempos): F, p, Mauchly, ε de Greenhouse-Geisser/Huynh-Feldt e os p corrigidos (aov + Error() em R)."""
    ref = REF["rm"]["one"]
    res = run("AnovaRepeatedMeasures", data["rm"], RM_BASE)
    w = rm_within(res)
    row = w[("tempo", "None")]
    assert row["num Df"] == ref["tempo"]["df"]
    close(row["Sum Sq"], ref["tempo"]["ss"]); close(row["F value"], ref["tempo"]["F"]); close(row["p"], ref["tempo"]["p"])
    res_row = w[("Residuals", "None")]
    assert res_row["num Df"] == ref["resid"]["df"]; close(res_row["Sum Sq"], ref["resid"]["ss"])
    gg, hf = w[("tempo", "Greenhouse-Geisser")], w[("tempo", "Huynh-Feldt")]
    close(gg["num Df"], 2 * ref["sph"]["gg"]); close(gg["p"], ref["p_gg"])
    close(hf["num Df"], 2 * ref["sph"]["hf"]); close(hf["p"], ref["p_hf"])
    sp = table(res, "sphericityTable")["data"][0]
    close(sp["Test statistic"], ref["sph"]["W"]); close(sp["approxChi"], ref["sph"]["chi"]); close(sp["p-value"], ref["sph"]["p"])
    close(sp["GG eps"], ref["sph"]["gg"]); close(sp["HF eps"], ref["sph"]["hf"])


def test_repeated_measures_anova_with_between_factor_matches_R(data):
    """Delineamento misto (tempo intra × grupo entre): efeito de grupo (entre), tempo, interação; a interação entra sozinha no modelo."""
    ref = REF["rm"]["mixed"]
    res = run("AnovaRepeatedMeasures", data["rm"], {**RM_BASE, "betweenSubjectFactors": ["grupo"], "betweenModelTerms": [{"components": ["grupo"]}]})
    between = {r["case"]: r for r in table(res, "betweenTable")["data"]}
    assert between["grupo"]["num Df"] == ref["grupo"]["df"]
    close(between["grupo"]["F value"], ref["grupo"]["F"]); close(between["grupo"]["Pr(>F)"], ref["grupo"]["p"])
    w = rm_within(res)
    inter = next(v for (case, corr), v in w.items() if corr == "None" and "grupo" in case and "tempo" in case)
    close(w[("tempo", "None")]["F value"], ref["tempo"]["F"]); close(w[("tempo", "None")]["p"], ref["tempo"]["p"])
    close(inter["F value"], ref["inter"]["F"]); close(inter["p"], ref["inter"]["p"])
    close(w[("tempo", "Greenhouse-Geisser")]["p"], ref["p_gg_tempo"]); close(table(res, "sphericityTable")["data"][0]["GG eps"], ref["sph"]["gg"])
    close(table(res, "sphericityTable")["data"][0]["Test statistic"], ref["sph"]["W"])


def test_repeated_measures_posthoc_effect_size_and_descriptives_match_R(data):
    """Post hoc do fator intra = testes t pareados (erro não agrupado, df = n − 1) com Holm/Bonferroni; η² parcial = SQ/(SQ + SQres)."""
    ref = REF["rm"]
    res = run("AnovaRepeatedMeasures", data["rm"], {**RM_BASE, "postHocTerms": ["tempo"], "postHocCorrectionHolm": True, "postHocCorrectionBonferroni": True,
                                                    "effectSizeEstimates": True, "effectSizePartialEtaSquared": True, "effectSizeOmegaSquared": False, "descriptives": True})
    ph = {(r["contrast_A"], r["contrast_B"]): r for r in table(res, "postHocStandardContainer_tempo1")["data"]}
    assert len(ph) == len(ref["posthoc"]) == 3
    for want in ref["posthoc"]:
        got = ph[(want["a"], want["b"])]
        close(got["estimate"], want["estimate"]); close(got["t.ratio"], want["t"]); close(got["SE"], want["se"]); assert got["df"] == want["df"]
        close(got["holm"], want["holm"]); close(got["bonferroni"], want["bonferroni"])
    close(rm_within(res)[("tempo", "None")]["partialEta"], ref["one"]["partial_eta"])
    assert [r["tempo."] for r in table(res, "tableDescriptives")["data"]] == ["t1", "t2", "t3"]


def test_friedman_and_conover_match_R(data):
    """Friedman é opção da AnovaRepeatedMeasures (`friedmanWithinFactor`); o Conover do JASP segue a fórmula de Conover (1999) com gl = (n−1)(k−1)."""
    ref = REF["friedman"]
    opts = {"repeatedMeasuresFactors": [{"name": "cond", "levels": ["c1", "c2", "c3"]}], "repeatedMeasuresCells": ["c1", "c2", "c3"],
            "withinModelTerms": [{"components": ["cond"]}], "friedmanWithinFactor": ["cond"], "conoverTest": True}
    res = run("AnovaRepeatedMeasures", data["friedman"], opts)
    row = table(res, "friedmanTable")["data"][0]
    assert row["Factor"] == "cond" and row["df"] == ref["df"]
    close(row["chiSqr"], ref["chi"]); close(row["p"], ref["p"]); close(row["kendall"], ref["kendall"])
    cv = {(r["(I)"], r["(J)"]): r for r in table(res, "conoverContainer_cond")["data"]}
    assert len(cv) == len(ref["conover"]) == 3
    for want in ref["conover"]:
        got = cv[(want["a"], want["b"])]
        assert got["df"] == want["df"]
        close(abs(got["t"]), abs(want["t"])); close(got["pval"], want["p"]); close(got["bonferroni"], want["bonferroni"]); close(got["holm"], want["holm"])
    assert [cv[("c1", "c2")]["wA"], cv[("c1", "c2")]["wB"]] == [ref["rank_sums"][0], ref["rank_sums"][1]]
    off = run("AnovaRepeatedMeasures", data["friedman"], {**opts, "friedmanWithinFactor": [], "conoverTest": False})
    assert not [p for p in tables(off["results"]) if "friedman" in p.lower() or "conover" in p.lower()]


def test_single_predictor_regression_is_not_an_empty_model(data):
    """Bug que existia: `components: ["altura"]` virava escalar no JSON e o modelo com UM preditor ficava vazio (R² = 0, só o intercepto)."""
    ref = REF["one_predictor"]
    res = run("RegressionLinear", data["dbc"], {"dependent": "produtividade", "covariates": ["altura"], "factors": [], "modelFit": True, "coefficientEstimate": True,
                                               "modelTerms": [{"components": ["altura"], "name": "model1", "title": "Model 1"}]})
    summary = table(res, "summaryTable")["data"]
    assert len(summary) == 1
    close(summary[0]["R2"], ref["reg"]["R2"])
    coefs = {r["name"]: r for r in table(res, "coeffTable")["data"]}
    assert set(coefs) == {"(Intercept)", "altura"}, list(coefs)
    close(coefs["altura"]["unstandCoeff"], ref["reg"]["est"][1]); close(coefs["altura"]["SE"], ref["reg"]["se"][1]); close(coefs["altura"]["p"], ref["reg"]["p"][1])
    close(coefs["(Intercept)"]["unstandCoeff"], ref["reg"]["est"][0])


def test_single_predictor_logistic_matches_R(data):
    ref = REF["one_predictor"]["logit"]
    res = run("RegressionLogistic", data["nivel"], {"dependent": "nivel", "covariates": ["altura"], "factors": [], "coefficientEstimate": True,
                                                    "modelTerms": [{"components": ["altura"], "name": "model1", "title": "Model 1"}]})
    est = {r["param"]: r for r in table(res, "estimatesTable")["data"]}   # um único modelo (rótulo "M₀")
    assert set(est) == {"(Intercept)", "altura"}, list(est)
    close(est["altura"]["est"], ref["est"][1]); close(est["altura"]["se"], ref["se"][1]); close(est["altura"]["pval"], ref["p"][1])
    close(est["(Intercept)"]["est"], ref["est"][0])


LIKERT = ("lik", "c1")   # (dataset, coluna ordinal)


def test_likert_column_is_ordinal_and_the_engine_reads_it_by_role(data):
    """c1 chega ao worker como fator (ordinal), mas o JASP lê as variáveis pelo PAPEL (escalar): os números são os do R com a coluna numérica."""
    ref = REF["ordinal"]
    ds = httpx.get(f"{API}/datasets/{data['lik']}").json()
    assert {c["name"]: c["measurement"] for c in ds["columns"]}["c1"] == "ordinal"
    one = table(run("TTestOneSample", data["lik"], {"dependent": ["c1"], "testValue": 10, "student": True, "meanDifference": True}), "ttest")["data"][0]
    close(one["t"], ref["onesample"]["t"]); close(one["p"], ref["onesample"]["p"]); close(one["m"], ref["onesample"]["diff"])
    pr = table(run("TTestPairedSamples", data["lik"], {"pairs": [["c1", "c2"]], "student": True}), "ttest")["data"][0]
    close(pr["t"], ref["paired"]["t"]); close(pr["p"], ref["paired"]["p"])
    ind = table(run("TTestIndependentSamples", data["lik"], {"dependent": ["c1"], "group": "grupo", "student": True}), "ttest")["data"][0]
    close(ind["Statistic"], ref["indep"]["t"]); close(ind["p"], ref["indep"]["p"])
    bf = table(run("TTestBayesianPairedSamples", data["lik"], {"pairs": [["c1", "c2"]]}), "ttestTable")["data"][0]["BF"]
    close(bf, ref["bayes_paired"], rel=1e-4)


def test_likert_column_in_anova_ancova_and_repeated_measures_matches_R(data):
    ref = REF["ordinal"]
    an = {r["cases"]: r for r in table(run("Anova", data["lik"], {"dependent": "c1", "fixedFactors": ["grupo"], "modelTerms": [{"components": ["grupo"]}]}), "anovaTable")["data"]}
    close(an["grupo"]["F value"], ref["anova"]["F"]); close(an["grupo"]["Pr(>F)"], ref["anova"]["p"])
    ac = {r["cases"]: r for r in table(run("Ancova", data["lik"], {"dependent": "c2", "fixedFactors": ["grupo"], "covariates": ["c1"],
                                                                 "modelTerms": [{"components": ["grupo"]}, {"components": ["c1"]}]}), "anovaTable")["data"]}
    for name, f, p in zip(ref["ancova"]["terms"], ref["ancova"]["F"], ref["ancova"]["p"]):
        close(ac[name]["F value"], f); close(ac[name]["Pr(>F)"], p)
    rm = run("AnovaRepeatedMeasures", data["lik"], {**RM_BASE_C, "sphericityTests": False})
    close(next(r for r in table(rm, "withinAnovaTable")["data"] if r["case"] == "cond")["F value"], ref["rm"]["F"])


RM_BASE_C = {"repeatedMeasuresFactors": [{"name": "cond", "levels": ["c1", "c2", "c3"]}], "repeatedMeasuresCells": ["c1", "c2", "c3"], "withinModelTerms": [{"components": ["cond"]}]}


def test_likert_column_in_regression_and_logistic_matches_R(data):
    ref = REF["ordinal"]
    reg = run("RegressionLinear", data["lik"], {"dependent": "c2", "covariates": ["c1"], "factors": [], "modelFit": True, "coefficientEstimate": True,
                                               "modelTerms": [{"components": ["c1"], "name": "model1", "title": "Model 1"}]})
    close(table(reg, "summaryTable")["data"][0]["R2"], ref["reg_cov"]["R2"])
    c = {r["name"]: r for r in table(reg, "coeffTable")["data"]}
    close(c["c1"]["unstandCoeff"], ref["reg_cov"]["est"][1]); close(c["c1"]["p"], ref["reg_cov"]["p"][1])
    dep = run("RegressionLinear", data["lik"], {"dependent": "c1", "covariates": ["c2"], "factors": [], "modelFit": True, "coefficientEstimate": True,
                                               "modelTerms": [{"components": ["c2"], "name": "model1", "title": "Model 1"}]})
    close(table(dep, "summaryTable")["data"][0]["R2"], ref["reg_dep"]["R2"])
    lg = run("RegressionLogistic", data["lik"], {"dependent": "nivel", "covariates": ["c1"], "factors": [], "coefficientEstimate": True,
                                                 "modelTerms": [{"components": ["c1"], "name": "model1", "title": "Model 1"}]})
    est = {r["param"]: r for r in table(lg, "estimatesTable")["data"]}
    close(est["c1"]["est"], ref["logit"]["est"][1]); close(est["c1"]["pval"], ref["logit"]["p"][1])


def test_friedman_accepts_a_likert_ordinal_column(data):
    """O Friedman (ranks) com c1 ordinal dá o mesmo χ² da fixture com c1 escalar (os postos não mudam)."""
    res = run("AnovaRepeatedMeasures", data["lik"], {**RM_BASE_C, "friedmanWithinFactor": ["cond"]})
    close(table(res, "friedmanTable")["data"][0]["chiSqr"], REF["friedman"]["chi"])


def ztable(res):
    return table(res, "ztest")["data"][0]


def test_z_test_two_means_with_known_sigma_matches_R(data):
    """Análise própria (custom.R, R base): z = (m1 − m2)/√(σ1²/n1 + σ2²/n2); não passa pelo JASP."""
    ref = REF["z_means"]
    opts = {"dependent": "score", "group": "group", "sigma1": ref["s1"], "sigma2": ref["s2"], "descriptives": True}
    res = run("ZTestMeans", data["tt"], opts)
    row = ztable(res)
    close(row["z"], ref["z"]); close(row["p"], ref["p"]); close(row["d"], ref["diff"]); close(row["se"], ref["se"])
    close(row["lo"], ref["lo"]); close(row["hi"], ref["hi"]); close(row["cd"], ref["d"])
    assert row["g"] == "a − b"
    g = {r["g"]: r for r in table(res, "desc")["data"]}
    assert g["a"]["n"] == ref["n1"] and g["b"]["n"] == ref["n2"]; close(g["a"]["m"], ref["m1"]); close(g["b"]["m"], ref["m2"])
    close(ztable(run("ZTestMeans", data["tt"], {**opts, "alternative": "greater"}))["p"], ref["p_greater"])
    one = ztable(run("ZTestMeans", data["tt"], {**opts, "alternative": "less"}))
    close(one["p"], ref["p_less"]); assert one["lo"] == float("-inf") or one["lo"] in ("-Infinity", "-Inf", None) or one["lo"] < -1e300


def test_z_test_two_proportions_matches_prop_test(data):
    """z (proporção agrupada) = ±√X² de prop.test(correct = FALSE); IC de Wald da diferença; sucesso = 2ª categoria (sim)."""
    ref = REF["z_props2"]
    res = run("ZTestProportions", data["resp"], {"outcome": "resposta", "group": "grupo"})
    row = ztable(res)
    close(row["p1"], ref["p1"]); close(row["p2"], ref["p2"]); close(row["d"], ref["diff"]); close(row["z"], ref["z"]); close(row["p"], ref["p"])
    close(row["lo"], ref["lo"]); close(row["hi"], ref["hi"])
    assert f"a ({ref['x1']}/{ref['n1']}) − b ({ref['x2']}/{ref['n2']})" == row["g"]
    close(ztable(run("ZTestProportions", data["resp"], {"outcome": "resposta", "group": "grupo", "alternative": "greater"}))["p"], ref["p_greater"])
    inv = ztable(run("ZTestProportions", data["resp"], {"outcome": "resposta", "group": "grupo", "invert": True}))   # sucesso = "nao": proporções complementares
    close(inv["p1"], 1 - ref["p1"]); close(inv["z"], -ref["z"]); close(inv["p"], ref["p"])


def test_z_test_one_proportion_matches_prop_test(data):
    ref = REF["z_props1"]
    row = ztable(run("ZTestProportions", data["resp"], {"outcome": "resposta", "p0": ref["p0"]}))
    assert row["x"] == ref["x"] and row["n"] == ref["n"]
    close(row["ph"], ref["ph"]); close(row["z"], ref["z"]); close(row["p"], ref["p"]); close(row["lo"], ref["lo"]); close(row["hi"], ref["hi"])   # IC de Wilson


def test_z_tests_reject_bad_requests(data):
    def post(an, opts, ds="tt"):
        return httpx.post(f"{API}/analyses/run", json={"analysis": an, "dataset_id": data[ds], "options": opts}, timeout=60)
    assert post("ZTestMeans", {"dependent": "score", "group": "group", "sigma1": 0, "sigma2": 1}).status_code == 422          # σ deve ser > 0
    assert post("ZTestMeans", {"dependent": "score", "group": "score", "sigma1": 1, "sigma2": 1}).status_code == 422          # grupo com muitos níveis
    assert post("ZTestMeans", {"dependent": "score", "group": "group", "sigma1": 1, "sigma2": 1, "alternative": "x"}).status_code == 422
    assert post("ZTestMeans", {"dependent": "score", "group": "group", "inventada": 1}).status_code == 422                      # opção desconhecida
    assert post("ZTestProportions", {"outcome": "score"}).status_code == 422                                                    # desfecho com > 2 categorias
    assert post("ZTestProportions", {"outcome": "resposta", "p0": 1.5}, "resp").status_code == 422


def test_regression_diagnostics_vif_and_durbin_watson_match_R(data):
    """As notas automáticas de regressão (lib/assumptions.ts) leem VIF do coeffTable e DW do summaryTable."""
    ref = REF["diag"]
    for ds, preds, vif, dw in (("colin", ["altura", "altura2"], ref["vif_collinear"], ref["dw_collinear"]), ("dbc", ["altura", "diametro"], ref["vif_ok"], ref["dw_ok"])):
        res = run("RegressionLinear", data[ds], {"dependent": "produtividade", "covariates": preds, "factors": [], "modelFit": True, "coefficientEstimate": True,
                                                "collinearityStatistic": True, "residualDurbinWatson": True,
                                                "modelTerms": [{"components": preds, "name": "model1", "title": "Model 1"}]})
        vifs = {r["name"]: r["VIF"] for r in table(res, "coeffTable")["data"] if r["name"] != "(Intercept)"}
        assert set(vifs) == set(preds)
        for v in vifs.values(): close(v, vif)
        close(table(res, "summaryTable")["data"][0]["DW"], dw)
    assert ref["vif_collinear"] > 10 > ref["vif_ok"]   # o conjunto "colin" realmente dispara o aviso; o "dbc", não


def test_chi_square_expected_counts_table_matches_R(data):
    """A regra de Cochran das notas automáticas usa as frequências esperadas do JASP (iguais às de chisq.test)."""
    ref = REF["chi"]
    res = run("ContingencyTables", data["faixas"], {"rows": ["grupo"], "columns": ["faixa"], "countsExpected": True, "chiSquared": True})
    rows = [r for r in table(res, "crossTabMain")["data"] if r["grupo"] != "Total"]
    got = [r[f"{lvl}[expected]"] for r in rows for lvl in ref["levels"]]
    # `expected` do R vem em ordem de coluna (grupo × faixa, coluna a coluna); comparamos como conjunto ordenado
    assert len(got) == len(ref["expected"]) == 6
    for g, w in zip(sorted(got), sorted(ref["expected"])):
        close(g, w)


def test_correlation_pairwise_shapiro_table_exists(data):
    res = run("Correlation", data["dbc"], {"variables": ["produtividade", "altura", "diametro"], "pearson": True, "assumptionCheckPairwiseShapiro": True})
    rows = table(res, "pairwiseShapiro")["data"]
    assert len(rows) == 3 and {(r["var1"], r["var2"]) for r in rows} == {("produtividade", "altura"), ("produtividade", "diametro"), ("altura", "diametro")}
    assert all(0 < r["W"] <= 1 and 0 <= r["p"] <= 1 for r in rows)


def test_paired_t_with_several_pairs_matches_R(data):
    """`pairs` com vários pares (inclusive a mesma coluna em dois pares): uma linha por par, na ordem pedida."""
    ref = REF["paired_multi"]
    pairs = [[r["a"], r["b"]] for r in ref]
    res = run("TTestPairedSamples", data["colin"], {"pairs": pairs, "student": True, "meanDifference": True})
    rows = table(res, "ttest")["data"]
    assert [(r["v1"], r["v2"]) for r in rows] == [tuple(p) for p in pairs]
    for got, want in zip(rows, ref):
        assert got["df"] == want["df"]
        close(got["t"], want["t"]); close(got["p"], want["p"]); close(got["md"], want["diff"])
    bf = table(run("TTestBayesianPairedSamples", data["colin"], {"pairs": pairs}), "ttestTable")["data"]
    assert [(r["variable1"], r["variable2"]) for r in bf] == [tuple(p) for p in pairs]   # o bayesiano também devolve uma linha por par
    nt = table(run("TTestPairedSamples", data["colin"], {"pairs": pairs, "student": True, "normalityTest": True}), "ttestNormalTable")["data"]
    assert len(nt) == len(pairs)   # as notas de normalidade das diferenças (6.5) cobrem cada par


def test_bayesian_correlation_matches_Ly_et_al(data):
    """BF10 da correlação de Pearson (prior beta esticado, κ = 1) = BF analítico de Ly, Verhagen & Wagenmakers (2016) integrado em R."""
    ref = REF["bayes_corr"]
    res = run("CorrelationBayesian", data["dbc"], {"variables": ["produtividade", "altura", "diametro"], "pearson": True})
    rows = {(r["variable1"], r["variable2"]): r for r in table(res, "corBayesTable")["data"]}
    assert len(rows) == 3
    for want in ref:
        got = rows[(want["a"], want["b"])]
        close(got["pearsonstat"], want["r"]); close(got["pearsonbf"], want["bf10"], rel=1e-5)
    wide = run("CorrelationBayesian", data["dbc"], {"variables": ["produtividade", "altura"], "pearson": True, "priorWidth": 0.5})   # κ = 0,5: prior mais concentrado
    close(table(wide, "corBayesTable")["data"][0]["pearsonbf"], next(x for x in ref if (x["a"], x["b"]) == ("produtividade", "altura"))["bf10"], rel=0.5)  # muda, mas é do mesmo porte
    assert table(wide, "corBayesTable")["data"][0]["pearsonbf"] != rows[("produtividade", "altura")]["pearsonbf"]


def test_bayesian_linear_regression_matches_lmBF(data):
    """BF de cada modelo contra o nulo (lmBF, JZS r = 0,354). O JASP lista os modelos ordenados e com 'Null model' na tabela."""
    ref = REF["bayes_reg"]
    res = run("RegressionLinearBayesian", data["dbc"], {"dependent": "produtividade", "covariates": ["altura", "diametro"],
                                                       "modelTerms": [{"components": "altura", "isNuisance": False}, {"components": "diametro", "isNuisance": False}]})
    rows = {r["Models"]: r for r in table(res, "modelComparisonTable")["data"]}
    assert set(rows) == {"Null model", "altura", "diametro", "altura + diametro"}, list(rows)
    null = rows["Null model"]["BF"]
    for name, key in (("altura", "altura"), ("diametro", "diametro"), ("altura + diametro", "both")):
        close(rows[name]["BF"] / null, ref[key], rel=1e-4)


def test_bayesian_ancova_matches_lmBF(data):
    ref = REF["bayes_ancova"]
    res = run("AncovaBayesian", data["dbc"], {"dependent": "produtividade", "fixedFactors": ["tratamento"], "covariates": ["altura"],
                                             "modelTerms": [{"components": ["tratamento"]}, {"components": ["altura"]}], "setSeed": True, "seed": 1})
    rows = {r["Models"]: r for r in table(res, "tableModelComparison")["data"]}
    assert set(rows) == {"Null model", "tratamento", "altura", "tratamento + altura"}, list(rows)   # modelo aditivo: sem a interação (remendo do modelTerms)
    null = rows["Null model"]["BF10"]
    close(rows["tratamento"]["BF10"] / null, ref["trat"], rel=1e-4); close(rows["altura"]["BF10"] / null, ref["altura"], rel=1e-4)
    close(rows["tratamento + altura"]["BF10"] / null, ref["both"], rel=0.05)   # envolve Monte Carlo (erro de ~1%)


def test_bayesian_contingency_tables_match_contingencyTableBF(data):
    ref = REF["bayes_chi"]
    for model, key in (("poisson", "poisson"), ("jointMultinomial", "joint"), ("independentMultinomialRowsFixed", "rows_fixed"), ("independentMultinomialColumnsFixed", "cols_fixed")):
        res = run("ContingencyTablesBayesian", data["faixas"], {"rows": ["grupo"], "columns": ["faixa"], "samplingModel": model, "priorConcentration": 1})
        row = table(res, "contTabBasBF")["data"][0]
        close(row["value[BF]"], ref[key], rel=1e-5)
        assert row["value[N]"] == 80


ANCOVA_BASE = {"dependent": "produtividade", "fixedFactors": ["tratamento"], "covariates": ["altura"], "modelTerms": [{"components": ["tratamento"]}, {"components": ["altura"]}]}


def test_ancova_adjusted_marginal_means_match_R(data):
    """Médias marginais ajustadas pela covariável (altura na sua média): predict() do lm em R."""
    ref = REF["ancova_adj"]
    res = run("Ancova", data["dbc"], {**ANCOVA_BASE, "marginalMeanTerms": ["tratamento"]})
    rows = {str(r["tratamento"]): r for r in table(res, "marginalMeansContainer_tratamento")["data"]}
    assert list(rows) == ref["levels"]
    for lvl, m, se in zip(ref["levels"], ref["lsmean"], ref["se"]):
        close(rows[lvl]["lsmean"], m); close(rows[lvl]["SE"], se)


def test_ancova_posthoc_tukey_holm_bonferroni_match_R(data):
    ref = REF["ancova_adj"]
    res = run("Ancova", data["dbc"], {**ANCOVA_BASE, "postHocTerms": ["tratamento"], "postHocTypeStandard": True,
                                      "postHocCorrectionTukey": True, "postHocCorrectionHolm": True, "postHocCorrectionBonferroni": True})
    rows = {(str(r["contrast_A"]), str(r["contrast_B"])): r for r in table(res, "postHocStandardContainer_tratamento1")["data"]}
    assert len(rows) == len(ref["pairs"]) == 28
    for want in ref["pairs"]:
        got = rows[(want["a"], want["b"])]
        assert got["df"] == ref["df"]
        close(got["estimate"], want["est"]); close(got["SE"], want["se"]); close(got["t.ratio"], want["t"])
        close(got["tukey"], want["tukey"], rel=1e-4); close(got["holm"], want["holm"]); close(got["bonferroni"], want["bonferroni"])


STEP_PREDS = ["altura", "diametro", "altura2"]


def logit_steps(data, method, blocks):
    opts = {"dependent": "nivel", "covariates": STEP_PREDS, "factors": [], "coefficientEstimate": True, "method": method, "modelTerms": blocks}
    return run("RegressionLogistic", data["steps"], opts)


def test_logistic_stepwise_methods_match_R_step(data):
    """Seleção por AIC: o JASP só percorre os passos com DOIS blocos (um vazio, 'forçado', e os candidatos). O último modelo = step() do R."""
    forced = {"components": [], "name": "model0", "title": "Model 0"}
    cand = {"components": STEP_PREDS, "name": "model1", "title": "Model 1"}
    for method in ("backward", "forward", "stepwise"):
        ref = REF["logit_steps"][method]
        res = logit_steps(data, method, [forced, cand])
        summary = table(res, "modelSummary")["data"]
        close(summary[-1]["aic"], ref["aic"])
        est = [r for r in table(res, "estimatesTable")["data"] if r["model"] == summary[-1]["mod"]]
        want_terms = [ref["terms"]] if isinstance(ref["terms"], str) else ref["terms"]   # o JSON do R guarda um termo único como texto
        assert [r["param"] for r in est if r["param"] != "(Intercept)"] == want_terms, method
        for got, want_est, want_se in zip(est, ref["est"], ref["se"]):
            close(got["est"], want_est, rel=1e-5); close(got["se"], want_se, rel=1e-5)
    # backward começa no modelo cheio e o AIC cai a cada passo; forward começa no nulo
    back = [r["aic"] for r in table(logit_steps(data, "backward", [forced, cand]), "modelSummary")["data"]]
    assert back == sorted(back, reverse=True) and len(back) >= 2
    assert len(table(logit_steps(data, "enter", [cand]), "modelSummary")["data"]) == 1   # 'enter': um modelo, todos os preditores


RM2_COLS = ["a1b1", "a1b2", "a1b3", "a2b1", "a2b2", "a2b3"]
RM2_FACTORS = [{"name": "A", "levels": ["pre", "pos"]}, {"name": "B", "levels": ["b1", "b2", "b3"]}]
RM2_BASE = {"repeatedMeasuresFactors": RM2_FACTORS, "repeatedMeasuresCells": RM2_COLS,
            "withinModelTerms": [{"components": ["A"]}, {"components": ["B"]}, {"components": ["A", "B"]}], "sphericityCorrectionNone": True}


def test_repeated_measures_two_within_factors_match_R(data):
    """Dois fatores intra-sujeito: as colunas em ordem (1º fator varia mais devagar), efeitos principais e interação (aov + Error())."""
    ref = REF["rm2"]
    res = run("AnovaRepeatedMeasures", data["rm2"], RM2_BASE)
    w = {(r["case"], r.get("correction", "None")): r for r in table(res, "withinAnovaTable")["data"]}   # só uma correção: a tabela não traz a coluna `correction`
    inter_key = next(k for k in w if "A" in k[0] and "B" in k[0] and k[0] != "Residuals")
    for key, name in ((("A", "None"), "A"), (("B", "None"), "B"), (inter_key, "AB")):
        row, want = w[key], ref[name]
        assert row["num Df"] == want["df"]
        close(row["Sum Sq"], want["ss"]); close(row["F value"], want["F"]); close(row["p"], want["p"])


def test_repeated_measures_two_factors_posthoc_is_paired_t_on_marginal_means(data):
    ref = REF["rm2"]
    res = run("AnovaRepeatedMeasures", data["rm2"], {**RM2_BASE, "postHocTerms": ["B"], "postHocCorrectionHolm": True, "postHocCorrectionBonferroni": True})
    rows = {(r["contrast_A"], r["contrast_B"]): r for r in table(res, "postHocStandardContainer_B1")["data"]}
    assert len(rows) == 3
    for want in ref["posthoc_B"]:
        got = rows[(want["a"], want["b"])]
        assert got["df"] == want["df"]
        close(got["estimate"], want["est"]); close(got["t.ratio"], want["t"]); close(got["holm"], want["holm"]); close(got["bonferroni"], want["bonferroni"])
    desc = run("AnovaRepeatedMeasures", data["rm2"], {**RM2_BASE, "descriptives": True})
    rows = table(desc, "tableDescriptives")["data"]
    assert [(r["A."], r["B."]) for r in rows] == [("pre", "b1"), ("pre", "b2"), ("pre", "b3"), ("pos", "b1"), ("pos", "b2"), ("pos", "b3")]   # ordem das células


INF = {"normal": {"informativeStandardizedEffectSize": "normal", "informativeNormalMean": 0.3, "informativeNormalStd": 0.5},
       "cauchy": {"informativeStandardizedEffectSize": "cauchy", "informativeCauchyLocation": 0.3, "informativeCauchyScale": 0.5},
       "t": {"informativeStandardizedEffectSize": "t", "informativeTLocation": 0.3, "informativeTScale": 0.5, "informativeTDf": 4}}


def test_informative_priors_in_bayesian_t_tests_match_numerical_integration(data):
    """BF10 com prior informativo = ∫ f(t|δ) π(δ) dδ / f(t|0) (t não central) integrado em R. Convenção: δ = (μ1 − μ2)/σ, grupo 1 = 1º nível."""
    ref = REF["bayes_inf"]
    for kind, extra in INF.items():
        one = run("TTestBayesianOneSample", data["dbc"], {"dependent": ["produtividade"], "testValue": 200, "effectSizeStandardized": "informative", **extra})
        close(table(one, "ttestTable")["data"][0]["BF"], ref["one"][kind], rel=1e-5)
        ind = run("TTestBayesianIndependentSamples", data["tt"], {"dependent": ["score"], "group": "group", "effectSizeStandardized": "informative", **extra})
        close(table(ind, "ttestTable")["data"][0]["BF"], ref["indep"][kind], rel=1e-5)
    default = table(run("TTestBayesianOneSample", data["dbc"], {"dependent": ["produtividade"], "testValue": 200}), "ttestTable")["data"][0]["BF"]
    assert default != ref["one"]["normal"]   # o prior informativo muda o resultado em relação ao Cauchy padrão
