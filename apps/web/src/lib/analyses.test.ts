import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { Column, Dataset, Measurement } from "../api";
import {
  ANALYSES, ANALYSIS_GROUPS, BAYES_ANCOVA_DEF, BAYES_CONTINGENCY_DEF, BAYES_CORRELATION_DEF, BAYES_REGRESSION_DEF, ZTEST_MEANS_DEF, ZTEST_PROPORTIONS_DEF, groupedAnalyses, isNumericDtype, ordinalAsScale, RM_ANOVA_DEF, ANCOVA_DEF, ANOVA_DEF, BAYES_ANOVA_DEF, BAYES_ONESAMPLE_TTEST_DEF, BAYES_PAIRED_TTEST_DEF, BAYES_TTEST_DEF, CONTINGENCY_DEF, LOGISTIC_DEF, CORRELATION_DEF, DESCRIPTIVES_DEF, ONESAMPLE_TTEST_DEF, PAIRED_TTEST_DEF, REGRESSION_DEF, TTEST_DEF,
  candidates, defaultState, fromOptions, getDef, isComplete, problems, resolveState, toOptions, type FormState,
} from "./analyses";

const col = (name: string, measurement: Measurement, n_distinct: number | null = null): Column => ({ name, dtype: measurement === "scale" ? "DOUBLE" : "VARCHAR", measurement, n_distinct });
const ds = (columns: Column[]): Dataset => ({ id: "a".repeat(32), name: "d.csv", table_name: "d", n_rows: 40, created_at: "", columns });
const DBC = ds([col("trat", "ordinal", 8), col("bloco", "ordinal", 4), col("prod", "scale"), col("altura", "scale"), col("grupo", "nominal", 2), col("regiao", "nominal", 4)]);
const state = (vars: Record<string, string[]>, values: FormState["values"] = {}, base?: FormState): FormState => {
  const b = base ?? { vars: {}, values: {} };
  return { vars: { ...b.vars, ...vars }, values: { ...b.values, ...values } };
};
const resolve = (def: Parameters<typeof resolveState>[0], d: Dataset, s: FormState) => resolveState(def, d, s);

describe("catálogo", () => {
  it("ids únicos e conhecidos pelo worker", () => {
    expect(new Set(ANALYSES.map((a) => a.id)).size).toBe(ANALYSES.length);
    expect(ANALYSES.map((a) => a.id)).toEqual(["TTestIndependentSamples", "TTestPairedSamples", "TTestOneSample", "Anova", "Ancova", "AnovaRepeatedMeasures", "ZTestMeans", "ZTestProportions", "Correlation", "RegressionLinear", "RegressionLogistic", "ContingencyTables", "Descriptives",
      "TTestBayesianIndependentSamples", "TTestBayesianPairedSamples", "TTestBayesianOneSample", "AnovaBayesian", "AncovaBayesian", "CorrelationBayesian", "RegressionLinearBayesian", "ContingencyTablesBayesian"]);
    expect(getDef("Anova")).toBe(ANOVA_DEF);
    expect(getDef("Inexistente")).toBeUndefined();
  });
  it("todo id do catálogo está no registro fechado do motor (engine.R): senão o worker responde 422", () => {
    const dir = "../../../../engines/r-worker/";
    const engine = readFileSync(fileURLToPath(new URL(`${dir}engine.R`, import.meta.url)), "utf8");
    const custom = readFileSync(fileURLToPath(new URL(`${dir}custom.R`, import.meta.url)), "utf8");
    // registro dos módulos JASP (engine.R) + análises próprias (custom.R: CUSTOM_ANALYSES)
    const registry = engine.slice(engine.indexOf("ANALYSIS_MODULE <- c("), engine.indexOf("ALLOWED_ANALYSES")) + custom.slice(custom.indexOf("CUSTOM_ANALYSES <- list("));
    for (const a of ANALYSES) expect(registry, a.id).toMatch(new RegExp(`\\b${a.id}\\s*=`));
  });
  it("o seletor agrupa todas as análises, cada uma em exatamente um grupo, sem ids fantasmas", () => {
    const ids = ANALYSIS_GROUPS.flatMap((g) => g.ids);
    expect([...ids].sort()).toEqual(ANALYSES.map((a) => a.id).sort());
    expect(groupedAnalyses().flatMap((g) => g.defs)).toHaveLength(ANALYSES.length);
    expect(ANALYSIS_GROUPS.every((g) => g.ids.length > 0)).toBe(true);
  });
  it("chaves de opção não se repetem dentro de uma análise (uma sobrescreveria a outra)", () => {
    for (const def of ANALYSES) {
      const keys = [...def.slots.map((s) => s.key), ...def.sections.flatMap((s) => s.items.map((i) => i.key))];
      expect(new Set(keys).size, def.id).toBe(keys.length);
    }
  });
});

describe("resolveState", () => {
  it("t-test: preenche a dependente e prefere, para o agrupamento, a coluna de 2 níveis", () => {
    const r = resolve(TTEST_DEF, DBC, defaultState(TTEST_DEF));
    expect(r.vars.dependent).toEqual(["prod"]);
    expect(r.vars.group).toEqual(["grupo"]); // trat (8) e bloco (4) vêm antes na tabela, mas só `grupo` tem 2 níveis
  });
  it("campo único mantém só uma coluna; multi remove duplicatas", () => {
    const r = resolve(ANOVA_DEF, DBC, state({ dependent: ["prod", "altura"], fixedFactors: ["trat", "trat", "bloco"] }));
    expect(r.vars.dependent).toEqual(["prod"]);
    expect(r.vars.fixedFactors).toEqual(["trat", "bloco"]);
  });
  it("descarta colunas que sumiram ou cujo nível de medida mudou (ex.: bloco virou escalar)", () => {
    const changed = ds(DBC.columns.map((c) => (c.name === "bloco" ? { ...c, measurement: "scale" as const } : c)));
    const r = resolve(ANOVA_DEF, changed, state({ dependent: ["prod"], fixedFactors: ["trat", "bloco", "fantasma"] }));
    expect(r.vars.fixedFactors).toEqual(["trat"]);
  });
  it("qui-quadrado: linhas e colunas obrigatórias recebem colunas DIFERENTES", () => {
    const r = resolve(CONTINGENCY_DEF, DBC, defaultState(CONTINGENCY_DEF));
    expect(r.vars.rows).toHaveLength(1);
    expect(r.vars.columns).toHaveLength(1);
    expect(r.vars.rows[0]).not.toBe(r.vars.columns[0]);
  });
  it("sem candidatos não inventa nada", () => {
    expect(resolve(ANOVA_DEF, ds([col("a", "nominal", 3)]), defaultState(ANOVA_DEF)).vars.dependent).toEqual([]);
  });
  it("valor de tipo errado volta ao padrão; valor certo é mantido", () => {
    const r = resolve(CORRELATION_DEF, DBC, state({}, { pearson: "sim" as unknown as boolean, ciLevel: NaN, alternative: "xyz", spearman: true }, defaultState(CORRELATION_DEF)));
    expect(r.values).toMatchObject({ pearson: true, ciLevel: 0.95, alternative: "twoSided", spearman: true });
  });
  it("candidates respeita os níveis aceitos e a preferência", () => {
    expect(candidates(ANOVA_DEF.slots[1], DBC).map((c) => c.name)).toEqual(["trat", "bloco", "grupo", "regiao"]);
    expect(candidates(CORRELATION_DEF.slots[0], DBC).map((c) => c.name)).toEqual(["trat", "bloco", "prod", "altura"]); // escalar + ordinal
    expect(candidates(TTEST_DEF.slots[0], undefined)).toEqual([]);
  });
});

describe("problems", () => {
  const p = (def: Parameters<typeof resolveState>[0], d: Dataset, s: FormState) => problems(def, d, resolve(def, d, s));
  it("válido => lista vazia", () => {
    expect(p(ANOVA_DEF, DBC, state({ fixedFactors: ["trat", "bloco"] }, {}, defaultState(ANOVA_DEF)))).toEqual([]);
    expect(p(TTEST_DEF, DBC, defaultState(TTEST_DEF))).toEqual([]);
  });
  it("campo obrigatório vazio: pede a escolha; sem candidatos manda ajustar o nível de medida", () => {
    expect(p(ANOVA_DEF, DBC, defaultState(ANOVA_DEF))).toEqual(["Escolha fatores."]);
    const msg = p(ANOVA_DEF, ds([col("a", "nominal", 3)]), defaultState(ANOVA_DEF));
    expect(msg[0]).toMatch(/Nenhuma coluna escalar disponível para “Variável dependente”.*aba Dados/);
  });
  it("correlação exige 2+ variáveis", () => {
    expect(p(CORRELATION_DEF, DBC, state({ variables: ["prod"] }, {}, defaultState(CORRELATION_DEF)))).toEqual(["Escolha ao menos 2 em “Variáveis”."]);
    expect(p(CORRELATION_DEF, DBC, state({ variables: ["prod", "altura"] }, { pearson: false }, defaultState(CORRELATION_DEF)))).toEqual(["Selecione ao menos um coeficiente."]);
  });
  it("t-test: agrupamento com níveis demais é recusado com a explicação certa; sem teste marcado também", () => {
    expect(p(TTEST_DEF, DBC, state({ group: ["regiao"] }, {}, defaultState(TTEST_DEF)))).toEqual(["regiao tem 4 níveis, e o teste t compara exatamente 2 grupos. Escolha outra variável ou filtre os dados (aba Consulta SQL)."]);
    expect(p(TTEST_DEF, DBC, state({}, { student: false, welch: false, mannWhitneyU: false }, defaultState(TTEST_DEF)))).toEqual(["Selecione ao menos um teste."]);
    expect(p(TTEST_DEF, ds([col("y", "scale"), col("g", "nominal", 1)]), defaultState(TTEST_DEF))[0]).toMatch(/g tem 1 nível,/);
  });
  it("ANOVA: fator de 1 nível; coluna repetida em dois campos", () => {
    expect(p(ANOVA_DEF, ds([col("y", "scale"), col("f", "nominal", 1)]), state({ fixedFactors: ["f"] }, {}, defaultState(ANOVA_DEF)))[0]).toMatch(/f tem 1 nível; um fator precisa de pelo menos 2/);
    const dup = ds([col("y", "scale"), col("x", "scale")]);
    expect(p(REGRESSION_DEF, dup, state({ dependent: ["y"], covariates: ["y", "x"] }, {}, defaultState(REGRESSION_DEF)))).toEqual(["“y” está em mais de um campo."]);
  });
  it("regressão exige covariável ou fator; qui-quadrado recusa muitos níveis", () => {
    expect(p(REGRESSION_DEF, DBC, defaultState(REGRESSION_DEF))).toEqual(["Escolha ao menos uma covariável ou um fator."]);
    const big = ds([col("a", "nominal", 40), col("b", "nominal", 3)]);
    expect(p(CONTINGENCY_DEF, big, defaultState(CONTINGENCY_DEF))[0]).toMatch(/a tem 40 níveis.*máximo 30/);
  });
  it("sem dataset", () => {
    expect(problems(ANOVA_DEF, undefined, defaultState(ANOVA_DEF))).toEqual(["Escolha um dataset."]);
  });
});

describe("toOptions — o contrato com o motor JASP", () => {
  const full = (def: Parameters<typeof resolveState>[0], d: Dataset, s: FormState) => toOptions(def, resolve(def, d, s));

  it("t-test: dependente em lista, agrupamento em texto, flags no nível raiz", () => {
    expect(full(TTEST_DEF, DBC, defaultState(TTEST_DEF))).toEqual({
      dependent: ["prod"], group: "grupo", student: true, welch: true, mannWhitneyU: false,
      descriptives: true, descriptivesPlot: false, effectSize: true, normalityTest: false, equalityOfVariancesTest: false,
    });
  });
  it("ANOVA: dependente em texto, fatores em vetor, modelTerms só com efeitos principais, Tukey para todos os fatores", () => {
    const o = full(ANOVA_DEF, DBC, state({ fixedFactors: ["trat", "bloco"] }, {}, defaultState(ANOVA_DEF)));
    expect(o.dependent).toBe("prod");
    expect(o.fixedFactors).toEqual(["trat", "bloco"]);
    expect(o.modelTerms).toEqual([{ components: ["trat"] }, { components: ["bloco"] }]);
    expect(o.postHocTerms).toEqual(["trat", "bloco"]);
    expect(o.postHocCorrectionTukey).toBe(true);
    expect(o.effectSizeEstimates).toBe(false);
    expect(o).not.toHaveProperty("interactions"); // valor só da interface não vaza para o motor
  });
  it("ANOVA: Kruskal-Wallis desligado por padrão; ligado, vale para todos os fatores e Dunn/efeito só com ele", () => {
    const off = full(ANOVA_DEF, DBC, state({ fixedFactors: ["trat", "bloco"] }, {}, defaultState(ANOVA_DEF)));
    expect(off.kruskalWallisFactors).toEqual([]);
    expect(off.postHocTypeDunn).toBe(false);
    expect(off.kruskalEffectSizeEstimates).toBe(false);
    for (const k of ["kruskal", "kruskalEffect", "dunn"]) expect(off).not.toHaveProperty(k); // só da interface
    const on = full(ANOVA_DEF, DBC, state({ fixedFactors: ["trat", "bloco"] }, { kruskal: true, kruskalEffect: true, dunn: true }, defaultState(ANOVA_DEF)));
    expect(on.kruskalWallisFactors).toEqual(["trat", "bloco"]);
    expect(on.kruskalEffectSizeEstimates).toBe(true);
    expect(on.kruskalEpsilon).toBe(true);
    expect(on.postHocTypeDunn).toBe(true);
    // Dunn marcado, mas Kruskal desligado: nada vai ao motor
    const orphan = full(ANOVA_DEF, DBC, state({ fixedFactors: ["trat"] }, { kruskal: false, dunn: true }, defaultState(ANOVA_DEF)));
    expect(orphan.postHocTypeDunn).toBe(false);
  });
  it("ANOVA bayesiana: modelo aditivo por padrão, interações só se pedidas, semente fixa e opções do prior/BF", () => {
    const ds1 = ds([col("y", "scale"), col("A", "nominal", 2), col("B", "nominal", 3)]);
    const o = full(BAYES_ANOVA_DEF, ds1, state({ fixedFactors: ["A", "B"] }, {}, defaultState(BAYES_ANOVA_DEF)));
    expect(o.modelTerms).toEqual([{ components: ["A"] }, { components: ["B"] }]);
    expect(o.setSeed).toBe(true);
    expect(o.seed).toBe(1);
    expect(o.cauchyPriorScaleFixedEffects).toBe(0.5);
    expect(o.bayesFactorType).toBe("BF10");
    expect(o).not.toHaveProperty("interactions");
    const full2 = full(BAYES_ANOVA_DEF, ds1, state({ fixedFactors: ["A", "B"] }, { interactions: true }, defaultState(BAYES_ANOVA_DEF)));
    expect(full2.modelTerms).toEqual([{ components: ["A"] }, { components: ["B"] }, { components: ["A", "B"] }]);
  });
  it("t bayesiano: prior 0,707, BF10 e hipótese bilateral por padrão; pareado monta `pairs`; grupo precisa de 2 níveis", () => {
    const d2 = ds([col("y", "scale"), col("z", "scale"), col("g", "nominal", 2)]);
    const ind = full(BAYES_TTEST_DEF, d2, state({ dependent: ["y"], group: ["g"] }, {}, defaultState(BAYES_TTEST_DEF)));
    expect(ind).toMatchObject({ dependent: ["y"], group: "g", priorWidth: 0.707, bayesFactorType: "BF10", alternative: "twoSided" });
    const pair = full(BAYES_PAIRED_TTEST_DEF, d2, state({ first: ["y"], second: ["z"] }, {}, defaultState(BAYES_PAIRED_TTEST_DEF)));
    expect(pair.pairs).toEqual([["y", "z"]]);
    expect(pair).not.toHaveProperty("first");
    expect(full(BAYES_ONESAMPLE_TTEST_DEF, d2, state({ dependent: ["y"] }, { testValue: 5 }, defaultState(BAYES_ONESAMPLE_TTEST_DEF))).testValue).toBe(5);
    const bad = ds([col("y", "scale"), col("g", "nominal", 3)]);
    expect(problems(BAYES_TTEST_DEF, bad, resolveState(BAYES_TTEST_DEF, bad, state({ dependent: ["y"], group: ["g"] }, {}, defaultState(BAYES_TTEST_DEF))))[0]).toMatch(/exatamente 2 grupos/);
  });
  it("t de uma amostra: teste z desligado por padrão (σ = 1 do JASP); ligado, envia zTest/zTestSd; é um teste válido sozinho", () => {
    const d1 = ds([col("y", "scale")]);
    const base = state({ dependent: ["y"] }, {}, defaultState(ONESAMPLE_TTEST_DEF));
    const off = full(ONESAMPLE_TTEST_DEF, d1, base);
    expect(off).toMatchObject({ zTest: false, zTestSd: 1, student: true });
    const on = full(ONESAMPLE_TTEST_DEF, d1, state({ dependent: ["y"] }, { zTest: true, zTestSd: 30, student: false }, defaultState(ONESAMPLE_TTEST_DEF)));
    expect(on).toMatchObject({ zTest: true, zTestSd: 30, student: false });
    const only = problems(ONESAMPLE_TTEST_DEF, d1, resolveState(ONESAMPLE_TTEST_DEF, d1, state({ dependent: ["y"] }, { zTest: true, student: false, wilcoxon: false }, defaultState(ONESAMPLE_TTEST_DEF))));
    expect(only).toEqual([]);
    const none = problems(ONESAMPLE_TTEST_DEF, d1, resolveState(ONESAMPLE_TTEST_DEF, d1, state({ dependent: ["y"] }, { zTest: false, student: false, wilcoxon: false }, defaultState(ONESAMPLE_TTEST_DEF))));
    expect(none).toEqual(["Selecione ao menos um teste."]);
  });
  it("ANOVA de medidas repetidas: níveis = colunas na ORDEM escolhida, fator com o nome dado, entre-sujeitos opcional", () => {
    const d3 = ds([col("t1", "scale"), col("t2", "scale"), col("t3", "scale"), col("grupo", "nominal", 2)]);
    const st = (cells: string[], between: string[], values = {}) => state({ repeatedMeasuresCells: cells, betweenSubjectFactors: between }, values, defaultState(RM_ANOVA_DEF));
    const o = full(RM_ANOVA_DEF, d3, st(["t3", "t1", "t2"], []));   // a ordem de marcação vale (t3, t1, t2), não a das colunas
    expect(o.repeatedMeasuresCells).toEqual(["t3", "t1", "t2"]);
    expect(o.repeatedMeasuresFactors).toEqual([{ name: "tempo", levels: ["t3", "t1", "t2"] }]);
    expect(o.withinModelTerms).toEqual([{ components: ["tempo"] }]);
    expect(o.betweenModelTerms).toEqual([]);
    expect(o.postHocTerms).toEqual([]);
    expect(o.effectSizeEstimates).toBe(false);
    for (const k of ["factorName", "posthoc"]) expect(o).not.toHaveProperty(k);   // só da interface
    const mixed = full(RM_ANOVA_DEF, d3, st(["t1", "t2"], ["grupo"], { factorName: "  momento ", posthoc: true, effectSizePartialEtaSquared: true }));
    expect(mixed.repeatedMeasuresFactors).toEqual([{ name: "momento", levels: ["t1", "t2"] }]);
    expect(mixed.betweenModelTerms).toEqual([{ components: ["grupo"] }]);
    expect(mixed.betweenSubjectFactors).toEqual(["grupo"]);
    expect(mixed.postHocTerms).toEqual(["momento"]);
    expect(mixed.effectSizeEstimates).toBe(true);
  });
  it("ANOVA de medidas repetidas: Friedman desligado por padrão; ligado vale para o fator intra, e Conover só com ele", () => {
    const d3 = ds([col("t1", "scale"), col("t2", "scale"), col("grupo", "nominal", 2)]);
    const st = (values = {}) => state({ repeatedMeasuresCells: ["t1", "t2"], betweenSubjectFactors: ["grupo"] }, values, defaultState(RM_ANOVA_DEF));
    const off = full(RM_ANOVA_DEF, d3, st());
    expect(off.friedmanWithinFactor).toEqual([]);
    expect(off.conoverTest).toBe(false);
    const on = full(RM_ANOVA_DEF, d3, st({ friedman: true, conover: true, factorName: "visita" }));
    expect(on.friedmanWithinFactor).toEqual(["visita"]);
    expect(on.conoverTest).toBe(true);
    expect(on).not.toHaveProperty("friedmanBetweenFactor");   // com agrupamento o Conover do JASP devolve NaN
    expect(full(RM_ANOVA_DEF, d3, st({ friedman: false, conover: true })).conoverTest).toBe(false);   // Conover órfão não vai ao motor
    for (const k of ["friedman", "conover"]) expect(on).not.toHaveProperty(k);
    const back = fromOptions(RM_ANOVA_DEF, toOptions(RM_ANOVA_DEF, st({ friedman: true, conover: true })));
    expect(back.values).toMatchObject({ friedman: true, conover: true });
  });
  it("ANOVA de medidas repetidas: exige 2+ medidas, nome do fator preenchido e diferente das colunas; ida e volta preserva nome e post hoc", () => {
    const d3 = ds([col("t1", "scale"), col("t2", "scale"), col("grupo", "nominal", 2)]);
    const pr = (cells: string[], values = {}) => problems(RM_ANOVA_DEF, d3, resolveState(RM_ANOVA_DEF, d3, state({ repeatedMeasuresCells: cells, betweenSubjectFactors: [] }, values, defaultState(RM_ANOVA_DEF))));
    expect(pr(["t1"])[0]).toMatch(/Escolha ao menos 2/);
    expect(pr(["t1", "t2"])).toEqual([]);
    expect(pr(["t1", "t2"], { factorName: "   " })[0]).toMatch(/Dê um nome ao fator/);
    expect(pr(["t1", "t2"], { factorName: "t2" })[0]).toMatch(/não pode ser igual ao de uma coluna/);
    const s0 = state({ repeatedMeasuresCells: ["t2", "t1"], betweenSubjectFactors: ["grupo"] }, { factorName: "visita", posthoc: true, postHocCorrectionBonferroni: true }, defaultState(RM_ANOVA_DEF));
    const options = toOptions(RM_ANOVA_DEF, s0);
    expect(toOptions(RM_ANOVA_DEF, fromOptions(RM_ANOVA_DEF, options))).toEqual(options);
    expect(fromOptions(RM_ANOVA_DEF, options).values).toMatchObject({ factorName: "visita", posthoc: true });
    expect(fromOptions(RM_ANOVA_DEF, options).vars.repeatedMeasuresCells).toEqual(["t2", "t1"]);
  });
  it("ordinal NUMÉRICA (Likert) vale onde se pede escalar; ordinal de texto, nominal numérica e campos de fator ficam como estavam", () => {
    const likert: Column = { name: "likert", dtype: "BIGINT", measurement: "ordinal", n_distinct: 5 };
    const rotulos: Column = { name: "rotulos", dtype: "VARCHAR", measurement: "ordinal", n_distinct: 3 };
    const codigo: Column = { name: "codigo", dtype: "BIGINT", measurement: "nominal", n_distinct: 4 };
    const dec: Column = { name: "nota", dtype: "DECIMAL(21,1)", measurement: "ordinal", n_distinct: 6 };
    const real: Column = col("peso", "scale");
    const d = ds([likert, rotulos, codigo, dec, real, col("grupo", "nominal", 2)]);
    const dep = ANOVA_DEF.slots[0], factors = ANOVA_DEF.slots[1];
    expect(candidates(dep, d).map((c) => c.name)).toEqual(["peso", "likert", "nota"]);   // escalar de verdade primeiro; sem texto nem nominal
    expect(ordinalAsScale(dep, likert)).toBe(true);
    expect(ordinalAsScale(dep, rotulos)).toBe(false);
    expect(ordinalAsScale(dep, codigo)).toBe(false);
    expect(candidates(factors, d).map((c) => c.name)).toEqual(["likert", "rotulos", "codigo", "nota", "grupo"]);   // fator: como antes
    expect(candidates(factors, d).every((c) => !ordinalAsScale(factors, c))).toBe(true);
    // slots que já aceitam ordinal (correlação, descritivas) não são afetados
    expect(candidates(CORRELATION_DEF.slots[0], d).map((c) => c.name)).toEqual(["likert", "rotulos", "nota", "peso"]);
    expect(isNumericDtype("DECIMAL(21,1)")).toBe(true);
    expect(isNumericDtype("VARCHAR")).toBe(false);
  });
  it("Likert vira medida repetida, covariável e variável dependente; o preenchimento automático prefere a escalar genuína", () => {
    const likert: Column = { name: "c1", dtype: "BIGINT", measurement: "ordinal", n_distinct: 8 };
    const d = ds([likert, col("c2", "scale"), col("c3", "scale")]);
    const rm = resolveState(RM_ANOVA_DEF, d, state({ repeatedMeasuresCells: ["c1", "c2", "c3"], betweenSubjectFactors: [] }, {}, defaultState(RM_ANOVA_DEF)));
    expect(rm.vars.repeatedMeasuresCells).toEqual(["c1", "c2", "c3"]);   // c1 não é descartada
    expect(problems(RM_ANOVA_DEF, d, rm)).toEqual([]);
    const t1 = resolveState(TTEST_DEF, ds([likert, col("c2", "scale"), col("g", "nominal", 2)]), defaultState(TTEST_DEF));
    expect(t1.vars.dependent).toEqual(["c2"]);   // c1 (ordinal) aparece depois da escalar: autofill pega c2
    const only = resolveState(TTEST_DEF, ds([likert, col("g", "nominal", 2)]), defaultState(TTEST_DEF));
    expect(only.vars.dependent).toEqual(["c1"]);   // sem escalar, a Likert serve (antes: "Nenhuma coluna escalar disponível")
    const reg = resolveState(REGRESSION_DEF, d, state({ dependent: ["c2"], covariates: ["c1"], factors: [] }, {}, defaultState(REGRESSION_DEF)));
    expect(reg.vars.covariates).toEqual(["c1"]);
  });
  it("teste z de duas médias: σ por grupo, padrões e exigência de 2 grupos", () => {
    const d2 = ds([col("y", "scale"), col("g", "nominal", 2)]);
    const o = full(ZTEST_MEANS_DEF, d2, state({ dependent: ["y"], group: ["g"] }, { sigma1: 1.5, sigma2: 2 }, defaultState(ZTEST_MEANS_DEF)));
    expect(o).toMatchObject({ dependent: "y", group: "g", sigma1: 1.5, sigma2: 2, alternative: "twoSided", ciLevel: 0.95, descriptives: true });
    const bad = ds([col("y", "scale"), col("g", "nominal", 3)]);
    expect(problems(ZTEST_MEANS_DEF, bad, resolveState(ZTEST_MEANS_DEF, bad, state({ dependent: ["y"], group: ["g"] }, {}, defaultState(ZTEST_MEANS_DEF))))[0]).toMatch(/g tem 3 níveis.*exatamente 2/);
  });
  it("teste z de proporções: grupo opcional (vazio = uma amostra), sucesso invertível, desfecho com 2 categorias", () => {
    const d2 = ds([col("resp", "nominal", 2), col("g", "nominal", 2), col("o3", "nominal", 3)]);
    const one = full(ZTEST_PROPORTIONS_DEF, d2, state({ outcome: ["resp"], group: [] }, { p0: 0.4 }, defaultState(ZTEST_PROPORTIONS_DEF)));
    expect(one).toMatchObject({ outcome: "resp", group: "", p0: 0.4, invert: false, alternative: "twoSided" });
    const two = full(ZTEST_PROPORTIONS_DEF, d2, state({ outcome: ["resp"], group: ["g"] }, { invert: true }, defaultState(ZTEST_PROPORTIONS_DEF)));
    expect(two).toMatchObject({ group: "g", invert: true });
    const pr = (v: Record<string, string[]>) => problems(ZTEST_PROPORTIONS_DEF, d2, resolveState(ZTEST_PROPORTIONS_DEF, d2, state(v, {}, defaultState(ZTEST_PROPORTIONS_DEF))));
    expect(pr({ outcome: ["o3"], group: [] })[0]).toMatch(/o3 tem 3 níveis/);
    expect(pr({ outcome: ["resp"], group: ["o3"] })[0]).toMatch(/o3 tem 3 níveis/);
    expect(pr({ outcome: ["resp"], group: ["g"] })).toEqual([]);
  });
  it("regressão bayesiana: um termo por covariável (efeito principal), semente fixa, prior 0,354 e BF10 por padrão", () => {
    const d = ds([col("y", "scale"), col("a", "scale"), col("b", "scale")]);
    const o = full(BAYES_REGRESSION_DEF, d, state({ dependent: ["y"], covariates: ["a", "b"] }, {}, defaultState(BAYES_REGRESSION_DEF)));
    expect(o.modelTerms).toEqual([{ components: ["a"], isNuisance: false }, { components: ["b"], isNuisance: false }]);
    expect(o).toMatchObject({ dependent: "y", covariates: ["a", "b"], setSeed: true, seed: 1, jzsRScale: 0.354, bayesFactorType: "BF10", bayesFactorOrder: "bestModelTop" });
    expect(problems(BAYES_REGRESSION_DEF, d, resolveState(BAYES_REGRESSION_DEF, d, state({ dependent: ["y"], covariates: [] }, {}, defaultState(BAYES_REGRESSION_DEF))))[0]).toMatch(/covariáveis/i);
  });
  it("ANCOVA bayesiana: fatores + covariáveis como efeitos principais, interações só entre fatores e só se pedidas", () => {
    const d = ds([col("y", "scale"), col("A", "nominal", 2), col("B", "nominal", 3), col("x", "scale")]);
    const st = (values = {}) => state({ dependent: ["y"], fixedFactors: ["A", "B"], covariates: ["x"] }, values, defaultState(BAYES_ANCOVA_DEF));
    expect(full(BAYES_ANCOVA_DEF, d, st()).modelTerms).toEqual([{ components: ["A"] }, { components: ["B"] }, { components: ["x"] }]);
    expect(full(BAYES_ANCOVA_DEF, d, st({ interactions: true })).modelTerms).toEqual([{ components: ["A"] }, { components: ["B"] }, { components: ["x"] }, { components: ["A", "B"] }]);
    expect(full(BAYES_ANCOVA_DEF, d, st())).toMatchObject({ setSeed: true, seed: 1, cauchyPriorScaleFixedEffects: 0.5, cauchyPriorScaleCovariates: 0.354, effects: true });
  });
  it("correlação e qui-quadrado bayesianos: defaults do prior, modelo amostral e campos herdados", () => {
    const d = ds([col("a", "scale"), col("b", "scale"), col("g", "nominal", 2), col("h", "nominal", 3)]);
    expect(full(BAYES_CORRELATION_DEF, d, state({ variables: ["a", "b"] }, {}, defaultState(BAYES_CORRELATION_DEF)))).toMatchObject({ variables: ["a", "b"], priorWidth: 1, alternative: "twoSided", bayesFactorType: "BF10" });
    expect(problems(BAYES_CORRELATION_DEF, d, resolveState(BAYES_CORRELATION_DEF, d, state({ variables: ["a"] }, {}, defaultState(BAYES_CORRELATION_DEF))))[0]).toMatch(/ao menos 2/);
    const chi = full(BAYES_CONTINGENCY_DEF, d, state({ rows: ["g"], columns: ["h"] }, { samplingModel: "poisson" }, defaultState(BAYES_CONTINGENCY_DEF)));
    expect(chi).toMatchObject({ rows: ["g"], columns: ["h"], samplingModel: "poisson", priorConcentration: 1, bayesFactorType: "BF10", countsObserved: true });
    expect(full(BAYES_CONTINGENCY_DEF, d, defaultState(BAYES_CONTINGENCY_DEF)).samplingModel).toBe("independentMultinomialRowsFixed");
  });
  it("ANCOVA: comparações dois a dois e médias marginais ajustadas são opt-in; ida e volta preserva", () => {
    const d = ds([col("y", "scale"), col("A", "nominal", 3), col("x", "scale")]);
    const st = (values = {}) => state({ dependent: ["y"], fixedFactors: ["A"], covariates: ["x"] }, values, defaultState(ANCOVA_DEF));
    const off = full(ANCOVA_DEF, d, st());
    expect(off).toMatchObject({ marginalMeanTerms: [], postHocTerms: [], postHocTypeStandard: false });
    for (const k of ["marginals", "posthoc"]) expect(off).not.toHaveProperty(k);
    const on = full(ANCOVA_DEF, d, st({ marginals: true, posthoc: true, postHocCorrectionHolm: true }));
    expect(on).toMatchObject({ marginalMeanTerms: ["A"], postHocTerms: ["A"], postHocTypeStandard: true, postHocCorrectionTukey: true, postHocCorrectionHolm: true });
    const back = fromOptions(ANCOVA_DEF, toOptions(ANCOVA_DEF, st({ marginals: true, posthoc: true })));
    expect(back.values).toMatchObject({ marginals: true, posthoc: true });
  });
  it("logística: `enter` = um modelo; backward/forward/stepwise = dois blocos (vazio + candidatos); dica de passos", () => {
    const d = ds([col("nivel", "nominal", 2), col("a", "scale"), col("b", "scale")]);
    const st = (values = {}) => state({ dependent: ["nivel"], covariates: ["a", "b"], factors: [] }, values, defaultState(LOGISTIC_DEF));
    expect(full(LOGISTIC_DEF, d, st()).modelTerms).toEqual([{ components: ["a", "b"], name: "model1", title: "Model 1" }]);
    expect(full(LOGISTIC_DEF, d, st()).method).toBe("enter");
    for (const method of ["backward", "forward", "stepwise"]) {
      const o = full(LOGISTIC_DEF, d, st({ method }));
      expect(o.method).toBe(method);
      expect(o.modelTerms).toEqual([{ components: [], name: "model0", title: "Model 0" }, { components: ["a", "b"], name: "model1", title: "Model 1" }]);
      expect(LOGISTIC_DEF.hint!(resolve(LOGISTIC_DEF, d, st({ method })))).toMatch(/cada passo.*último modelo é o selecionado/);
    }
    expect(LOGISTIC_DEF.hint!(resolve(LOGISTIC_DEF, d, st()))).toBeNull();
  });
  it("ANCOVA não oferece Kruskal-Wallis (o JASP só o tem na ANOVA)", () => {
    expect(ANCOVA_DEF.sections.flatMap((x) => x.items).some((i) => i.key.startsWith("kruskal"))).toBe(false);
  });
  it("Descritivas: tabelas de frequência desligadas por padrão e enviadas ao motor quando marcadas", () => {
    const ds1 = ds([col("g", "nominal", 3)]);
    expect(full(DESCRIPTIVES_DEF, ds1, state({ variables: ["g"] }, {}, defaultState(DESCRIPTIVES_DEF))).frequencyTables).toBe(false);
    expect(full(DESCRIPTIVES_DEF, ds1, state({ variables: ["g"] }, { frequencyTables: true }, defaultState(DESCRIPTIVES_DEF))).frequencyTables).toBe(true);
  });
  it("ANOVA: interações geradas por tamanho (principais, 2 a 2, 3 a 3)", () => {
    const o = full(ANOVA_DEF, ds([col("y", "scale"), col("A", "nominal", 2), col("B", "nominal", 2), col("C", "nominal", 2)]),
      state({ fixedFactors: ["A", "B", "C"] }, { interactions: true }, defaultState(ANOVA_DEF)));
    expect((o.modelTerms as { components: string[] }[]).map((t) => t.components.join(":"))).toEqual(["A", "B", "C", "A:B", "A:C", "B:C", "A:B:C"]);
  });
  it("ANOVA: com mais de 4 fatores as interações ficam limitadas (modelo legível)", () => {
    const cols = ["A", "B", "C", "D", "E"].map((n) => col(n, "nominal", 2));
    const o = full(ANOVA_DEF, ds([col("y", "scale"), ...cols]), state({ fixedFactors: ["A", "B", "C", "D", "E"] }, { interactions: true }, defaultState(ANOVA_DEF)));
    expect((o.modelTerms as unknown[]).length).toBe(5 + 11);
  });
  it("ANOVA: tamanho do efeito liga o interruptor mestre; sem correção marcada não há post hoc", () => {
    const o = full(ANOVA_DEF, DBC, state({ fixedFactors: ["trat"] }, { effectSizePartialEtaSquared: true, postHocCorrectionTukey: false }, defaultState(ANOVA_DEF)));
    expect(o.effectSizeEstimates).toBe(true);
    expect(o.postHocTerms).toEqual([]);
  });
  it("regressão: UM modelo com todos os preditores (no JASP cada entrada de modelTerms é um modelo, não um termo)", () => {
    const o = full(REGRESSION_DEF, DBC, state({ covariates: ["altura"], factors: ["grupo"] }, {}, defaultState(REGRESSION_DEF)));
    expect(o).toMatchObject({ dependent: "prod", covariates: ["altura"], factors: ["grupo"], modelFit: true });
    expect(o.modelTerms).toEqual([{ components: ["altura", "grupo"], name: "model1", title: "Model 1" }]);
    expect(full(REGRESSION_DEF, DBC, defaultState(REGRESSION_DEF)).modelTerms).toEqual([]); // sem preditores: sem modelo (e o formulário bloqueia a execução)
  });
  it("correlação e qui-quadrado", () => {
    expect(full(CORRELATION_DEF, DBC, state({ variables: ["prod", "altura"] }, { spearman: true }, defaultState(CORRELATION_DEF)))).toMatchObject({ variables: ["prod", "altura"], pearson: true, spearman: true, alternative: "twoSided", ciLevel: 0.95 });
    expect(full(CONTINGENCY_DEF, DBC, defaultState(CONTINGENCY_DEF))).toMatchObject({ rows: [expect.any(String)], columns: [expect.any(String)], chiSquared: true });
  });
});

describe("fromOptions — recuperar um bloco salvo", () => {
  const cases: [string, Parameters<typeof resolveState>[0], FormState][] = [
    ["t-test", TTEST_DEF, state({ dependent: ["prod"], group: ["grupo"] }, { welch: false, mannWhitneyU: true }, defaultState(TTEST_DEF))],
    ["ANOVA", ANOVA_DEF, state({ dependent: ["prod"], fixedFactors: ["trat", "bloco"] }, { interactions: true, effectSizeOmegaSquared: true, postHocCorrectionHolm: true, kruskal: true, kruskalEffect: true, dunn: true }, defaultState(ANOVA_DEF))],
    ["correlação", CORRELATION_DEF, state({ variables: ["prod", "altura"] }, { kendallsTauB: true, ci: true, ciLevel: 0.9, alternative: "greater" }, defaultState(CORRELATION_DEF))],
    ["regressão", REGRESSION_DEF, state({ dependent: ["prod"], covariates: ["altura"], factors: ["grupo"] }, { coefficientCi: true }, defaultState(REGRESSION_DEF))],
    ["qui-quadrado", CONTINGENCY_DEF, state({ rows: ["grupo"], columns: ["regiao"] }, { likelihoodRatio: true, percentagesRow: true }, defaultState(CONTINGENCY_DEF))],
  ];
  it.each(cases)("%s: opções -> estado -> opções é idêntico (ida e volta sem perder nada)", (_n, def, s) => {
    const options = toOptions(def, s);
    expect(toOptions(def, fromOptions(def, options))).toEqual(options);
  });
  it("opções incompletas ou de tipo errado não quebram (usam o padrão)", () => {
    const s = fromOptions(ANOVA_DEF, { dependent: 42, fixedFactors: "trat", descriptives: "talvez", modelTerms: "lixo" });
    expect(s.vars.dependent).toEqual([]);
    expect(s.vars.fixedFactors).toEqual(["trat"]);
    expect(s.values.descriptives).toBe(true);
    expect(s.values.interactions).toBe(false);
    expect(fromOptions(TTEST_DEF, {}).vars).toEqual({ dependent: [], group: [] });
  });
  it("detecta interações salvas", () => {
    expect(fromOptions(ANOVA_DEF, { modelTerms: [{ components: ["a"] }, { components: ["a", "b"] }] }).values.interactions).toBe(true);
    expect(fromOptions(ANOVA_DEF, { modelTerms: [{ components: ["a"] }] }).values.interactions).toBe(false);
  });
});

describe("isComplete (bloco de relatório sem precisar do dataset)", () => {
  it("exige os campos obrigatórios e o mínimo", () => {
    expect(isComplete(ANOVA_DEF, { dependent: "y", fixedFactors: ["a"] })).toBe(true);
    expect(isComplete(ANOVA_DEF, { dependent: "y", fixedFactors: [] })).toBe(false);
    expect(isComplete(ANOVA_DEF, {})).toBe(false);
    expect(isComplete(CORRELATION_DEF, { variables: ["a"] })).toBe(false);
    expect(isComplete(CORRELATION_DEF, { variables: ["a", "b"] })).toBe(true);
    expect(isComplete(TTEST_DEF, { dependent: [], group: "g" })).toBe(false);
    expect(isComplete(REGRESSION_DEF, { dependent: "y" })).toBe(true); // covariáveis/fatores são conferidos na execução
  });
});

describe("teste t pareado", () => {
  it("preenche as duas medidas com colunas escalares DIFERENTES e monta `pairs` (sem vazar os campos locais ao JASP)", () => {
    const r = resolve(PAIRED_TTEST_DEF, DBC, defaultState(PAIRED_TTEST_DEF));
    expect(r.vars.first).toEqual(["prod"]);
    expect(r.vars.second).toEqual(["altura"]);
    const o = toOptions(PAIRED_TTEST_DEF, r);
    expect(o.pairs).toEqual([["prod", "altura"]]);
    expect(o).not.toHaveProperty("first");
    expect(o).not.toHaveProperty("second");
  });
  it("ida e volta: `pairs` salvo volta aos dois campos e o bloco conta como completo", () => {
    const o = { pairs: [["prod", "altura"]], student: true };
    const s = fromOptions(PAIRED_TTEST_DEF, o);
    expect(s.vars).toEqual({ first: ["prod"], second: ["altura"], moreFirst: [], moreSecond: [] });
    expect(isComplete(PAIRED_TTEST_DEF, o)).toBe(true);
    expect(isComplete(PAIRED_TTEST_DEF, { pairs: [] })).toBe(false);
    expect(isComplete(PAIRED_TTEST_DEF, {})).toBe(false);
  });
  it("com uma só coluna escalar não há como formar o par: problema claro", () => {
    const one = ds([col("prod", "scale"), col("g", "nominal", 2)]);
    const r = resolve(PAIRED_TTEST_DEF, one, defaultState(PAIRED_TTEST_DEF));
    expect(problems(PAIRED_TTEST_DEF, one, r).join(" ")).toMatch(/2ª medida/i);
    expect(toOptions(PAIRED_TTEST_DEF, r).pairs).toEqual([]);
  });
  it("a mesma coluna nas duas medidas é recusada", () => {
    const r = state({ first: ["prod"], second: ["prod"] }, {}, defaultState(PAIRED_TTEST_DEF));
    expect(problems(PAIRED_TTEST_DEF, DBC, resolve(PAIRED_TTEST_DEF, DBC, r))).toEqual(["“prod” está em mais de um campo."]);
  });
});

describe("teste t pareado com vários pares", () => {
  const D4 = ds([col("a", "scale"), col("b", "scale"), col("c", "scale"), col("d", "scale"), col("g", "nominal", 2)]);
  const st = (v: Record<string, string[]>, values = {}) => state(v, values, defaultState(PAIRED_TTEST_DEF));
  it("monta `pairs` com o par principal + os adicionais, na ordem das listas", () => {
    const r = resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"], moreFirst: ["c"], moreSecond: ["d"] }));
    expect(toOptions(PAIRED_TTEST_DEF, r).pairs).toEqual([["a", "b"], ["c", "d"]]);
    expect(PAIRED_TTEST_DEF.hint!(r)).toBe("Pares formados: a − b; c − d.");
    expect(problems(PAIRED_TTEST_DEF, D4, r)).toEqual([]);
    expect(PAIRED_TTEST_DEF.hint!(resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"] })))).toBeNull();   // um par só: sem resumo
    for (const k of ["first", "second", "moreFirst", "moreSecond"]) expect(toOptions(PAIRED_TTEST_DEF, r)).not.toHaveProperty(k);
  });
  it("a mesma linha de base pode entrar em dois pares (campos compartilhados), mas não comparada com ela mesma nem repetida", () => {
    const base = resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"], moreFirst: ["a"], moreSecond: ["c"] }));
    expect(problems(PAIRED_TTEST_DEF, D4, base)).toEqual([]);
    expect(toOptions(PAIRED_TTEST_DEF, base).pairs).toEqual([["a", "b"], ["a", "c"]]);
    expect(problems(PAIRED_TTEST_DEF, D4, resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"], moreFirst: ["c"], moreSecond: ["c"] })))[0]).toMatch(/“c” não pode ser comparada com ela mesma/);
    expect(problems(PAIRED_TTEST_DEF, D4, resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"], moreFirst: ["a"], moreSecond: ["b"] })))[0]).toMatch(/O par a − b aparece mais de uma vez/);
  });
  it("listas de pares adicionais de tamanhos diferentes são recusadas com mensagem clara", () => {
    const r = resolve(PAIRED_TTEST_DEF, D4, st({ first: ["a"], second: ["b"], moreFirst: ["c", "d"], moreSecond: ["c"] }));
    expect(problems(PAIRED_TTEST_DEF, D4, r)[0]).toMatch(/mesmo número de medidas nas duas listas.*2 e 1/);
  });
  it("ida e volta de vários pares (e o bloco salvo com 1 par continua igual); o t pareado bayesiano herda tudo", () => {
    const o = { pairs: [["a", "b"], ["a", "c"], ["d", "c"]], student: true };
    const s = fromOptions(PAIRED_TTEST_DEF, o);
    expect(s.vars).toEqual({ first: ["a"], second: ["b"], moreFirst: ["a", "d"], moreSecond: ["c", "c"] });
    expect(toOptions(PAIRED_TTEST_DEF, s).pairs).toEqual(o.pairs);
    expect(isComplete(PAIRED_TTEST_DEF, o)).toBe(true);
    const bayes = toOptions(BAYES_PAIRED_TTEST_DEF, resolve(BAYES_PAIRED_TTEST_DEF, D4, state({ first: ["a"], second: ["b"], moreFirst: ["c"], moreSecond: ["d"] }, {}, defaultState(BAYES_PAIRED_TTEST_DEF))));
    expect(bayes.pairs).toEqual([["a", "b"], ["c", "d"]]);
    expect(BAYES_PAIRED_TTEST_DEF.hint!(resolve(BAYES_PAIRED_TTEST_DEF, D4, state({ first: ["a"], second: ["b"], moreFirst: ["c"], moreSecond: ["d"] }, {}, defaultState(BAYES_PAIRED_TTEST_DEF))))).toMatch(/a − b; c − d/);
  });
});

describe("teste t de uma amostra", () => {
  it("manda o valor de referência como número e a variável como lista", () => {
    const r = resolve(ONESAMPLE_TTEST_DEF, DBC, state({ dependent: ["prod"] }, { testValue: 200 }, defaultState(ONESAMPLE_TTEST_DEF)));
    expect(toOptions(ONESAMPLE_TTEST_DEF, r)).toMatchObject({ dependent: ["prod"], testValue: 200, student: true, alternative: "twoSided" });
  });
  it("exige uma variável escalar e ao menos um teste", () => {
    const empty = resolve(ONESAMPLE_TTEST_DEF, DBC, defaultState(ONESAMPLE_TTEST_DEF));
    expect(problems(ONESAMPLE_TTEST_DEF, DBC, empty).join(" ")).toMatch(/Escolha/);
    const none = resolve(ONESAMPLE_TTEST_DEF, DBC, state({ dependent: ["prod"] }, { student: false, wilcoxon: false }, defaultState(ONESAMPLE_TTEST_DEF)));
    expect(problems(ONESAMPLE_TTEST_DEF, DBC, none)).toContain("Selecione ao menos um teste.");
  });
});

describe("estatísticas descritivas", () => {
  it("aceita escalares e categóricas; `splitBy` é opcional e vai como lista", () => {
    const r = resolve(DESCRIPTIVES_DEF, DBC, state({ variables: ["prod", "altura", "grupo"] }, {}, defaultState(DESCRIPTIVES_DEF)));
    expect(r.vars.variables).toEqual(["prod", "altura", "grupo"]);
    const o = toOptions(DESCRIPTIVES_DEF, r);
    expect(o.splitBy).toEqual([]);
    expect(o).toMatchObject({ valid: true, meanArithmetic: true, sd: true, minimum: true, maximum: true, median: true, mode: false });
    const split = resolve(DESCRIPTIVES_DEF, DBC, state({ variables: ["prod"], splitBy: ["grupo"] }, {}, defaultState(DESCRIPTIVES_DEF)));
    expect(toOptions(DESCRIPTIVES_DEF, split).splitBy).toEqual(["grupo"]);
  });
  it("nível de confiança só aparece com o intervalo ligado", () => {
    const item = DESCRIPTIVES_DEF.sections.flatMap((s) => s.items).find((i) => i.key === "meanCiLevel")!;
    expect(item.showIf?.({ meanCi: false })).toBe(false);
    expect(item.showIf?.({ meanCi: true })).toBe(true);
  });
  it("não deixa separar por uma variável que também está sendo analisada", () => {
    const r = resolve(DESCRIPTIVES_DEF, DBC, state({ variables: ["grupo", "prod"], splitBy: ["grupo"] }, {}, defaultState(DESCRIPTIVES_DEF)));
    expect(problems(DESCRIPTIVES_DEF, DBC, r).join(" ")).toMatch(/grupo/);
  });
});

describe("ANCOVA", () => {
  const base = () => defaultState(ANCOVA_DEF);
  it("monta modelTerms com fatores e covariáveis como efeitos principais (aditivo, sem interação fantasma)", () => {
    const r = resolve(ANCOVA_DEF, DBC, state({ dependent: ["prod"], fixedFactors: ["trat", "bloco"], covariates: ["altura"] }, {}, base()));
    expect(toOptions(ANCOVA_DEF, r)).toMatchObject({
      dependent: "prod", fixedFactors: ["trat", "bloco"], covariates: ["altura"],
      modelTerms: [{ components: ["trat"] }, { components: ["bloco"] }, { components: ["altura"] }],
    });
  });
  it("interações só entre FATORES (nunca com a covariável) e só se pedidas", () => {
    const r = resolve(ANCOVA_DEF, DBC, state({ dependent: ["prod"], fixedFactors: ["trat", "bloco"], covariates: ["altura"] }, { interactions: true }, base()));
    const comps = (toOptions(ANCOVA_DEF, r).modelTerms as { components: string[] }[]).map((t) => t.components.join(":"));
    expect(comps).toEqual(["trat", "bloco", "altura", "trat:bloco"]);
  });
  it("exige ao menos um fator e uma covariável", () => {
    const r = resolve(ANCOVA_DEF, DBC, state({ dependent: ["prod"], fixedFactors: ["trat"] }, {}, base()));
    expect(problems(ANCOVA_DEF, DBC, r).join(" ")).toMatch(/covariáveis/i);
  });
  it("ida e volta: interações salvas voltam ligadas e o bloco conta como completo", () => {
    const o = { dependent: "prod", fixedFactors: ["trat", "bloco"], covariates: ["altura"], modelTerms: [{ components: ["trat", "bloco"] }] };
    expect(fromOptions(ANCOVA_DEF, o).values.interactions).toBe(true);
    expect(isComplete(ANCOVA_DEF, o)).toBe(true);
    expect(isComplete(ANCOVA_DEF, { ...o, covariates: [] })).toBe(false);
  });
});

describe("regressão logística", () => {
  it("prefere, para o desfecho, a coluna de 2 categorias, e monta UM modelo com todos os preditores", () => {
    const r = resolve(LOGISTIC_DEF, DBC, state({ covariates: ["altura"], factors: ["regiao"] }, {}, defaultState(LOGISTIC_DEF)));
    expect(r.vars.dependent).toEqual(["grupo"]); // trat (8), bloco (4) e regiao (4) vêm antes, mas só `grupo` tem 2 categorias
    expect(toOptions(LOGISTIC_DEF, r).modelTerms).toEqual([{ components: ["altura", "regiao"], name: "model1", title: "Model 1" }]);
  });
  it("desfecho com mais de 2 categorias é recusado com a saída sugerida (SQL + salvar como dataset)", () => {
    const r = state({ dependent: ["trat"], covariates: ["altura"] }, {}, defaultState(LOGISTIC_DEF));
    const msg = problems(LOGISTIC_DEF, DBC, resolve(LOGISTIC_DEF, DBC, r)).join(" ");
    expect(msg).toMatch(/8 níveis/);
    expect(msg).toMatch(/Salvar como dataset/);
  });
  it("sem preditores: problema claro; com o IC desligado, o nível de confiança não aparece", () => {
    const r = resolve(LOGISTIC_DEF, DBC, defaultState(LOGISTIC_DEF));
    expect(problems(LOGISTIC_DEF, DBC, r)).toContain("Escolha ao menos uma covariável ou um fator.");
    const lvl = LOGISTIC_DEF.sections.flatMap((x) => x.items).find((i) => i.key === "coefficientCiLevel")!;
    expect(lvl.showIf?.({ coefficientCi: false })).toBe(false);
    expect(lvl.showIf?.({ coefficientCi: true })).toBe(true);
  });
});
