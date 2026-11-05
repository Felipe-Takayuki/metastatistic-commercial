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
    for (const a of ["Correlation", "RegressionLinear", "ContingencyTables", "Descriptives"]) expect(assumptionOptions(a, {})).toBeNull();
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
