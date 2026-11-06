import { describe, expect, it } from "vitest";
import { assumptionNotes, assumptionOptions, fmtP } from "./assumptions";

const table = (data: Record<string, unknown>[]) => ({ schema: { fields: [] }, data });
/** Árvore no formato do jaspResults: as tabelas são achadas pelo fim do caminho. */
const tree = (tables: Record<string, Record<string, unknown>[]>) => ({
  results: Object.fromEntries(Object.entries(tables).map(([k, v]) => [k, table(v)])),
});

describe("assumptionOptions", () => {
  it("acrescenta os testes de pressuposto sem perder as opções do usuário", () => {
    expect(assumptionOptions("Anova", { dependent: "y", homogeneityTests: false })).toEqual({ dependent: "y", homogeneityTests: true });
    expect(assumptionOptions("TTestIndependentSamples", { student: true })).toEqual({ student: true, normalityTest: true, equalityOfVariancesTest: true });
  });
  it("não mexe nas opções recebidas e devolve null onde não há pressuposto verificável", () => {
    const o = { dependent: "y" };
    assumptionOptions("Anova", o);
    expect(o).toEqual({ dependent: "y" });
    for (const a of ["RegressionLogistic", "Descriptives", "TTestBayesianOneSample", "AnovaBayesian"]) expect(assumptionOptions(a, {})).toBeNull();
  });
});

describe("fmtP", () => {
  it("estilo APA com vírgula decimal", () => {
    expect(fmtP(0.0123)).toBe("p = ,012");
    expect(fmtP(0.0004)).toBe("p < ,001");
  });
});

describe("assumptionNotes", () => {
  it("t independente: normalidade e variâncias violadas viram dois avisos com a sugestão certa", () => {
    const n = assumptionNotes("TTestIndependentSamples", tree({
      "AssumptionChecks/ttestNormalTable": [{ dep: "score", W: 0.91, p: 0.004 }],
      "AssumptionChecks/equalityVariance": [{ variable: "score", fStat: 9.1, p: 0.003 }],
    }).results);
    expect(n.map((x) => x.level)).toEqual(["warn", "warn"]);
    expect(n[0].text).toMatch(/Normalidade rejeitada para score \(resíduos\).*W = 0,91.*p = ,004.*Mann-Whitney/);
    expect(n[1].text).toMatch(/Variâncias diferentes.*score.*Levene.*p = ,003.*Welch/);
  });
  it("pareado: o aviso fala das diferenças; uma amostra sugere Wilcoxon", () => {
    const pair = assumptionNotes("TTestPairedSamples", tree({ "A/ttestNormalTable": [{ v1: "antes", sep: "-", v2: "depois", W: 0.8, p: 0.01 }] }).results);
    expect(pair[0].text).toMatch(/antes − depois \(diferenças\).*Wilcoxon/);
    const one = assumptionNotes("TTestOneSample", tree({ "A/ttestNormalTable": [{ v: "y", W: 0.8, p: 0.01 }] }).results);
    expect(one[0].text).toMatch(/para y .*Wilcoxon/);
  });
  it("ANOVA: Levene violado sugere Kruskal-Wallis; ANCOVA não (a opção só existe na ANOVA)", () => {
    const t = tree({ "anovaContainer_assumptionsContainer_leveneTable": [{ F: 4.2, df1: 3, df2: 28, p: 0.01 }] }).results;
    expect(assumptionNotes("Anova", t)[0].text).toMatch(/Homogeneidade.*F = 4,20.*Kruskal-Wallis/);
    expect(assumptionNotes("Ancova", t)[0].text).not.toMatch(/Kruskal/);
  });
  it("medidas repetidas: esfericidade violada sugere Greenhouse-Geisser com o ε; respeitada = nota de nenhum alerta", () => {
    const bad = tree({ "rmAnovaContainer_assumptionsContainer_sphericityTable": [{ case: "tempo", "Test statistic": 0.52, "p-value": 0.004, "GG eps": 0.68, "HF eps": 0.74 }] }).results;
    const n = assumptionNotes("AnovaRepeatedMeasures", bad);
    expect(n[0].level).toBe("warn");
    expect(n[0].text).toMatch(/Esfericidade violada em tempo \(Mauchly, W = 0,52, p = ,004\).*Greenhouse-Geisser \(ε = 0,68\)/);
    const ok = tree({ "x_sphericityTable": [{ case: "tempo", "Test statistic": 0.86, "p-value": 0.2, "GG eps": 0.88 }] }).results;
    expect(assumptionNotes("AnovaRepeatedMeasures", ok)[0].level).toBe("ok");
    expect(assumptionOptions("AnovaRepeatedMeasures", { a: 1 })).toEqual({ a: 1, sphericityTests: true });
  });
  it("regressão: VIF > 10 e Durbin-Watson significativo viram avisos; VIF baixo e DW ok = nenhum alerta", () => {
    const bad = tree({ "modelContainer_coeffTable": [{ name: "(Intercept)", VIF: null }, { name: "altura", VIF: 52.3 }, { name: "peso", VIF: 3.1 }],
                       "modelContainer_summaryTable": [{ DW: 0.8, DW_p: 0.0004 }] }).results;
    const n = assumptionNotes("RegressionLinear", bad);
    expect(n.map((x) => x.level)).toEqual(["warn", "warn"]);
    expect(n[0].text).toMatch(/Multicolinearidade: VIF = 52,30 em altura/);
    expect(n.some((x) => /peso/.test(x.text))).toBe(false);
    expect(n[1].text).toMatch(/Autocorrelação dos resíduos \(Durbin-Watson = 0,80, p < ,001\).*ordem/);
    const ok = tree({ "m_coeffTable": [{ name: "altura", VIF: 1.003 }], "m_summaryTable": [{ DW: 2.5, DW_p: 0.13 }] }).results;
    expect(assumptionNotes("RegressionLinear", ok)).toEqual([{ level: "ok", text: expect.stringContaining("nenhum alerta") }]);
    expect(assumptionOptions("RegressionLinear", { dependent: "y" })).toEqual({ dependent: "y", coefficientEstimate: true, collinearityStatistic: true, residualDurbinWatson: true });
  });
  it("correlação: normalidade bivariada rejeitada sugere Spearman/Kendall", () => {
    const n = assumptionNotes("Correlation", tree({ "assumptionsContainer_pairwiseShapiro": [{ var1: "a", separator: "-", var2: "b", W: 0.8, p: 0.002 }, { var1: "a", separator: "-", var2: "c", W: 0.98, p: 0.7 }] }).results);
    expect(n).toHaveLength(1);
    expect(n[0].text).toMatch(/Normalidade bivariada rejeitada para a e b \(Shapiro-Wilk, W = 0,80, p = ,002\).*Spearman ou Kendall/);
  });
  it("qui-quadrado: regra de Cochran sobre as frequências esperadas (ignora totais)", () => {
    const row = (lvl: string, e: number[]) => ({ faixa: lvl, "a[expected]": e[0], "b[expected]": e[1], "total[expected]": e[0] + e[1] });
    const total = { faixa: "Total", "a[expected]": 40, "b[expected]": 40, "total[expected]": 80 };
    const few = tree({ "container_crossTabMain": [row("x", [1.6, 1.6]), row("y", [1.6, 1.6]), row("z", [20, 20]), total] }).results;
    const n = assumptionNotes("ContingencyTables", few);
    expect(n[0].text).toMatch(/4 de 6 células \(66,67%\) com frequência esperada abaixo de 5 \(mínima 1,60\)/);
    const fine = tree({ "c_crossTabMain": [row("x", [16.5, 16.5]), row("y", [10, 10]), total] }).results;
    expect(assumptionNotes("ContingencyTables", fine)[0].level).toBe("ok");
    // até 20% das células abaixo de 5 é aceitável (1 de 5); abaixo de 1 nunca é, nem com uma só célula pequena
    const one = (e: number) => ({ faixa: "x", "a[expected]": e, "total[expected]": e });
    const five = tree({ "c_crossTabMain": [one(4), one(9), one(9), one(9), one(9), { faixa: "Total", "a[expected]": 40, "total[expected]": 40 }] }).results;
    expect(assumptionNotes("ContingencyTables", five)[0].level).toBe("ok");
    const tiny = tree({ "c_crossTabMain": [one(0.5), one(9), one(9), one(9), one(9), { faixa: "Total", "a[expected]": 40, "total[expected]": 40 }] }).results;
    expect(assumptionNotes("ContingencyTables", tiny)[0].text).toMatch(/1 de 5 células \(20,00%\).*mínima 0,50/);
  });
  it("sem violações: um único aviso informativo", () => {
    const n = assumptionNotes("Anova", tree({ "x_leveneTable": [{ F: 1.4, df1: 7, df2: 24, p: 0.247 }] }).results);
    expect(n).toHaveLength(1);
    expect(n[0].level).toBe("ok");
  });
  it("p exatamente em 0,05 não é violação; tabelas ausentes ou p não numérico não geram nada", () => {
    expect(assumptionNotes("Anova", tree({ "x_leveneTable": [{ F: 1, df1: 1, df2: 1, p: 0.05 }] }).results)[0].level).toBe("ok");
    expect(assumptionNotes("Anova", tree({}).results)).toEqual([]);
    expect(assumptionNotes("Anova", tree({ "x_leveneTable": [{ p: "" }] }).results)).toEqual([]);
    expect(assumptionNotes("Anova", null)).toEqual([]);
  });
});
