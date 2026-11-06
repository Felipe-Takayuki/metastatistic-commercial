/**
 * Definições declarativas das análises estatísticas (formulário + mapeamento para as opções do JASP) e o motor genérico
 * que as usa. Escritas à mão de propósito: o QML do JASP monta os formulários a partir de componentes compartilhados
 * (construtor de termos do modelo, contrastes…) e gerá-los automaticamente produziria opções erradas.
 * Os nomes das opções vêm dos testes oficiais dos módulos JASP e são conferidos contra o motor nos testes de integração.
 */
import type { Column, Dataset, Measurement } from "../api";

export type Values = Record<string, boolean | number | string>;
export interface FormState { vars: Record<string, string[]>; values: Values }

export interface VarSlot {
  key: string;            // nome da opção JASP
  label: string;
  levels: Measurement[];  // níveis de medida aceitos
  multi: boolean;         // vários campos (lista de caixas) ou um só (seleção)
  asArray?: boolean;      // um só na tela, mas o JASP espera uma lista (ex.: `dependent` do teste t)
  required?: boolean;
  min?: number;           // multi: quantidade mínima
  autofill?: boolean;     // único e obrigatório: pré-seleciona o primeiro candidato livre
  preferLevels?: number;  // candidatos com exatamente N níveis vêm primeiro (agrupamento do teste t = 2)
  local?: boolean;        // só da interface: NÃO vai ao JASP (use `derive` para montar a opção real, ex.: `pairs`)
  shared?: boolean;       // a coluna pode repetir em outros campos (ex.: a mesma linha de base em dois pares); a conferência fica com `check`
  ordered?: boolean;      // multi: a ORDEM da escolha importa (ex.: níveis de um fator intra-sujeito) e é mostrada na tela
}

interface ItemBase { key: string; label: string; local?: boolean; showIf?: (v: Values) => boolean }
export interface ToggleItem extends ItemBase { type: "toggle"; default: boolean }
export interface NumberItem extends ItemBase { type: "number"; default: number; min: number; max: number; step: number }
export interface TextItem extends ItemBase { type: "text"; default: string; maxLength: number }
export interface ChoiceItem extends ItemBase { type: "choice"; default: string; options: { value: string; label: string }[] }
/** `local`: valor só da interface (não vai ao JASP; é usado por `derive`). */
export type Item = ToggleItem | NumberItem | TextItem | ChoiceItem;

export interface AnalysisDef {
  id: string;             // nome da função JASP
  title: string;
  description: string;
  slots: VarSlot[];
  sections: { title: string; items: Item[] }[];
  /** Opções calculadas a partir do estado (ex.: `modelTerms`). */
  derive?: (s: FormState) => Record<string, unknown>;
  /** Recupera valores `local` a partir de opções salvas. */
  parse?: (options: Record<string, unknown>) => Values;
  /** Recupera campos de variável `local` a partir de opções salvas (ex.: `pairs` -> primeira/segunda variável). */
  parseVars?: (options: Record<string, unknown>) => Record<string, string[]>;
  /** Texto de apoio (não bloqueia) mostrado abaixo dos campos de variável, ex.: os pares formados. */
  hint?: (s: FormState) => string | null;
  /** Problemas que impedem a execução (além dos campos obrigatórios). */
  check?: (ctx: { dataset: Dataset; state: FormState }) => string[];
}

const toggle = (key: string, label: string, def = false, extra: Partial<ToggleItem> = {}): ToggleItem => ({ type: "toggle", key, label, default: def, ...extra });
const levelsLabel = (n: number) => `${n} ${n === 1 ? "nível" : "níveis"}`;
const MEASURE_NAME: Record<Measurement, string> = { nominal: "nominal", ordinal: "ordinal", scale: "escalar" };
const colOf = (ds: Dataset, name: string) => ds.columns.find((c) => c.name === name);

/** Combinações de 2+ fatores (interações), por tamanho: A:B, A:C, B:C, A:B:C… */
function interactionTerms(factors: string[]): string[][] {
  const out: string[][] = [];
  const n = Math.min(factors.length, 4); // 4 fatores = 11 termos; acima disso o modelo fica ilegível
  for (let mask = 1; mask < 1 << n; mask++) {
    const combo = factors.slice(0, n).filter((_, i) => mask & (1 << i));
    if (combo.length >= 2) out.push(combo);
  }
  return out.sort((a, b) => a.length - b.length);
}

// ------------------------------------------------------------------------------------------------------------------
export const TTEST_DEF: AnalysisDef = {
  id: "TTestIndependentSamples",
  title: "Teste t independente",
  description: "Compara a média de uma variável escalar entre dois grupos.",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, asArray: true, required: true, autofill: true },
    { key: "group", label: "Variável de agrupamento (2 grupos)", levels: ["nominal", "ordinal"], multi: false, required: true, autofill: true, preferLevels: 2 },
  ],
  sections: [
    { title: "Testes", items: [toggle("student", "Student", true), toggle("welch", "Welch", true), toggle("mannWhitneyU", "Mann-Whitney")] },
    { title: "Adicionais", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("descriptivesPlot", "Gráfico descritivo"), toggle("effectSize", "Tamanho do efeito (d de Cohen)", true)] },
    { title: "Pressupostos", items: [toggle("normalityTest", "Normalidade (Shapiro-Wilk)"), toggle("equalityOfVariancesTest", "Igualdade de variâncias")] },
  ],
  check: ({ dataset, state }) => {
    const out: string[] = [];
    const g = state.vars.group[0];
    const n = g ? colOf(dataset, g)?.n_distinct ?? null : null;
    if (n !== null && n !== 2) out.push(`${g} tem ${levelsLabel(n)}, e o teste t compara exatamente 2 grupos. Escolha outra variável ou filtre os dados (aba Consulta SQL).`);
    if (!state.values.student && !state.values.welch && !state.values.mannWhitneyU) out.push("Selecione ao menos um teste.");
    return out;
  },
};

export const ANOVA_DEF: AnalysisDef = {
  id: "Anova",
  title: "ANOVA",
  description: "Compara a média de uma variável escalar entre os níveis de um ou mais fatores. Em delineamento em blocos casualizados, inclua o bloco como um fator (crie a coluna com SQL e “Salvar como dataset”).",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, required: true, autofill: true },
    { key: "fixedFactors", label: "Fatores (tratamento, bloco…)", levels: ["nominal", "ordinal"], multi: true, required: true, min: 1 },
  ],
  sections: [
    { title: "Modelo", items: [toggle("interactions", "Incluir interações entre os fatores", false, { local: true })] },
    { title: "Pressupostos", items: [toggle("homogeneityTests", "Homogeneidade de variâncias (Levene)"), toggle("qqPlot", "Gráfico Q-Q dos resíduos")] },
    { title: "Estatísticas", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("effectSizeEtaSquared", "η² (eta ao quadrado)"), toggle("effectSizePartialEtaSquared", "η² parcial"), toggle("effectSizeOmegaSquared", "ω² (ômega ao quadrado)")] },
    { title: "Comparações múltiplas (todos os fatores)", items: [toggle("postHocCorrectionTukey", "Tukey", true), toggle("postHocCorrectionBonferroni", "Bonferroni"), toggle("postHocCorrectionHolm", "Holm")] },
    {
      title: "Não paramétrico (um teste por fator)",
      items: [
        toggle("kruskal", "Teste de Kruskal-Wallis", false, { local: true }),
        toggle("kruskalEffect", "Tamanho de efeito (ε² e η² de postos)", false, { local: true, showIf: (v) => !!v.kruskal }),
        toggle("dunn", "Post hoc de Dunn (Bonferroni e Holm)", false, { local: true, showIf: (v) => !!v.kruskal }),
      ],
    },
  ],
  derive: (s) => {
    const f = s.vars.fixedFactors;
    const terms = f.map((x) => ({ components: [x] }));
    if (s.values.interactions) for (const combo of interactionTerms(f)) terms.push({ components: combo });
    const anyEffect = !!(s.values.effectSizeEtaSquared || s.values.effectSizePartialEtaSquared || s.values.effectSizeOmegaSquared);
    const anyPostHoc = !!(s.values.postHocCorrectionTukey || s.values.postHocCorrectionBonferroni || s.values.postHocCorrectionHolm);
    const kw = !!s.values.kruskal;
    return {
      modelTerms: terms, effectSizeEstimates: anyEffect, postHocTerms: anyPostHoc ? f : [],
      kruskalWallisFactors: kw ? f : [],
      kruskalEffectSizeEstimates: kw && !!s.values.kruskalEffect, kruskalEpsilon: true, kruskalEta: true,
      postHocTypeDunn: kw && !!s.values.dunn,
    };
  },
  parse: (o) => {
    const terms = Array.isArray(o.modelTerms) ? (o.modelTerms as { components?: unknown[] }[]) : [];
    return {
      interactions: terms.some((t) => Array.isArray(t.components) && t.components.length > 1),
      kruskal: Array.isArray(o.kruskalWallisFactors) && o.kruskalWallisFactors.length > 0,
      kruskalEffect: o.kruskalEffectSizeEstimates === true,
      dunn: o.postHocTypeDunn === true,
    };
  },
  check: ({ dataset, state }) =>
    state.vars.fixedFactors.flatMap((name) => {
      const n = colOf(dataset, name)?.n_distinct ?? null;
      return n !== null && n < 2 ? [`${name} tem ${levelsLabel(n)}; um fator precisa de pelo menos 2.`] : [];
    }),
};

export const CORRELATION_DEF: AnalysisDef = {
  id: "Correlation",
  title: "Correlação",
  description: "Mede a associação entre duas ou mais variáveis (matriz de correlações).",
  slots: [{ key: "variables", label: "Variáveis (2 ou mais)", levels: ["scale", "ordinal"], multi: true, required: true, min: 2 }],
  sections: [
    { title: "Coeficientes", items: [toggle("pearson", "Pearson", true), toggle("spearman", "Spearman"), toggle("kendallsTauB", "Kendall (tau-b)")] },
    {
      title: "Exibição",
      items: [
        toggle("pairwiseDisplay", "Lista de pares (em vez de matriz)"), toggle("significanceFlagged", "Marcar correlações significativas"), toggle("sampleSize", "Mostrar n"),
        toggle("ci", "Intervalo de confiança"),
        { type: "number", key: "ciLevel", label: "Nível de confiança", default: 0.95, min: 0.5, max: 0.999, step: 0.01, showIf: (v) => !!v.ci },
      ],
    },
    { title: "Gráficos", items: [toggle("scatterPlot", "Matriz de dispersão"), toggle("heatmapPlot", "Mapa de calor")] },
    {
      title: "Hipótese alternativa",
      items: [{ type: "choice", key: "alternative", label: "Hipótese alternativa", default: "twoSided", options: [{ value: "twoSided", label: "Bilateral (r ≠ 0)" }, { value: "greater", label: "Positiva (r > 0)" }, { value: "less", label: "Negativa (r < 0)" }] }],
    },
  ],
  check: ({ state }) => (!state.values.pearson && !state.values.spearman && !state.values.kendallsTauB ? ["Selecione ao menos um coeficiente."] : []),
};

export const REGRESSION_DEF: AnalysisDef = {
  id: "RegressionLinear",
  title: "Regressão linear",
  description: "Modela uma variável escalar a partir de covariáveis (escalares) e fatores (categóricos).",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, required: true, autofill: true },
    { key: "covariates", label: "Covariáveis (escalares)", levels: ["scale"], multi: true },
    { key: "factors", label: "Fatores (categóricos)", levels: ["nominal", "ordinal"], multi: true },
  ],
  sections: [
    {
      title: "Tabelas",
      items: [
        toggle("modelFit", "Ajuste do modelo (R², F)", true), toggle("coefficientEstimate", "Coeficientes", true), toggle("coefficientCi", "Intervalo de confiança dos coeficientes"),
        { type: "number", key: "coefficientCiLevel", label: "Nível de confiança", default: 0.95, min: 0.5, max: 0.999, step: 0.01, showIf: (v) => !!v.coefficientCi },
        toggle("descriptives", "Estatísticas descritivas"),
      ],
    },
    { title: "Diagnóstico", items: [toggle("collinearityStatistic", "Colinearidade (VIF e tolerância)"), toggle("residualDurbinWatson", "Durbin-Watson"), toggle("residualQqPlot", "Gráfico Q-Q dos resíduos"), toggle("residualVsFittedPlot", "Resíduos × valores ajustados")] },
  ],
  // No JASP, `modelTerms` da regressão é uma lista de MODELOS (blocos): uma entrada = um modelo com esses preditores.
  derive: (s) => {
    const predictors = [...s.vars.covariates, ...s.vars.factors];
    return { modelTerms: predictors.length ? [{ components: predictors, name: "model1", title: "Model 1" }] : [] };
  },
  check: ({ state }) => (state.vars.covariates.length + state.vars.factors.length === 0 ? ["Escolha ao menos uma covariável ou um fator."] : []),
};

export const CONTINGENCY_DEF: AnalysisDef = {
  id: "ContingencyTables",
  title: "Qui-quadrado (tabela de contingência)",
  description: "Testa a associação entre duas variáveis categóricas.",
  slots: [
    { key: "rows", label: "Linhas (categórica)", levels: ["nominal", "ordinal"], multi: false, asArray: true, required: true, autofill: true },
    { key: "columns", label: "Colunas (categórica)", levels: ["nominal", "ordinal"], multi: false, asArray: true, required: true, autofill: true },
  ],
  sections: [
    { title: "Testes", items: [toggle("chiSquared", "Qui-quadrado de Pearson", true), toggle("chiSquaredContinuityCorrection", "Correção de continuidade (Yates)"), toggle("likelihoodRatio", "Razão de verossimilhança")] },
    { title: "Associação", items: [toggle("phiAndCramersV", "Phi e V de Cramér"), toggle("contingencyCoefficient", "Coeficiente de contingência")] },
    { title: "Células", items: [toggle("countsExpected", "Contagens esperadas"), toggle("percentagesRow", "% por linha"), toggle("percentagesColumn", "% por coluna"), toggle("percentagesTotal", "% do total"), toggle("residualsStandardized", "Resíduos padronizados")] },
  ],
  check: ({ dataset, state }) =>
    [state.vars.rows[0], state.vars.columns[0]].flatMap((name) => {
      const n = name ? colOf(dataset, name)?.n_distinct ?? null : null;
      return n !== null && n > 30 ? [`${name} tem ${levelsLabel(n)}; uma tabela de contingência com tantos níveis fica ilegível (máximo 30).`] : [];
    }),
};

const alternative = (label: string): Item => ({
  type: "choice", key: "alternative", label, default: "twoSided",
  options: [{ value: "twoSided", label: "Diferente (bilateral)" }, { value: "greater", label: "Maior" }, { value: "less", label: "Menor" }],
});

/** Pares: o 1º vem dos campos "1ª/2ª medida"; os adicionais, das duas listas ordenadas (o i-ésimo de cada lista forma o par). */
export function pairsOf(s: FormState): string[][] {
  const out: string[][] = [];
  if (s.vars.first?.length && s.vars.second?.length) out.push([s.vars.first[0], s.vars.second[0]]);
  const f = s.vars.moreFirst ?? [], g = s.vars.moreSecond ?? [];
  for (let i = 0; i < Math.min(f.length, g.length); i++) out.push([f[i], g[i]]);
  return out;
}
const pairLabel = (p: string[]) => `${p[0]} − ${p[1]}`;
const pairsCheck = ({ state }: { state: FormState }): string[] => {
  const out: string[] = [];
  const f = state.vars.moreFirst ?? [], g = state.vars.moreSecond ?? [];
  if (f.length !== g.length) out.push(`Marque o mesmo número de medidas nas duas listas de pares adicionais (hoje: ${f.length} e ${g.length}); o i-ésimo de cada lista forma um par.`);
  const pairs = pairsOf(state);
  const same = pairs.find((p) => p[0] === p[1]);
  if (same) out.push(`“${same[0]}” não pode ser comparada com ela mesma (par ${pairLabel(same)}).`);
  const seen = new Set<string>();
  for (const p of pairs) {
    if (seen.has(pairLabel(p))) { out.push(`O par ${pairLabel(p)} aparece mais de uma vez.`); break; }
    seen.add(pairLabel(p));
  }
  return out;
};

export const PAIRED_TTEST_DEF: AnalysisDef = {
  id: "TTestPairedSamples",
  title: "Teste t pareado",
  description: "Compara duas medidas escalares da mesma unidade (antes/depois, duas variáveis nas mesmas linhas) pela diferença entre elas. Para vários pares de uma vez, use os campos de pares adicionais.",
  slots: [
    { key: "first", label: "1ª medida (escalar)", levels: ["scale"], multi: false, required: true, autofill: true, local: true },
    { key: "second", label: "2ª medida (escalar)", levels: ["scale"], multi: false, required: true, autofill: true, local: true },
    { key: "moreFirst", label: "Pares adicionais: 1ª medida de cada par (na ordem)", levels: ["scale"], multi: true, local: true, ordered: true, shared: true },
    { key: "moreSecond", label: "Pares adicionais: 2ª medida de cada par (na ordem)", levels: ["scale"], multi: true, local: true, ordered: true, shared: true },
  ],
  sections: [
    { title: "Testes", items: [toggle("student", "Student", true), toggle("wilcoxon", "Wilcoxon (postos sinalizados)")] },
    { title: "Adicionais", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("meanDifference", "Diferença média", true), toggle("effectSize", "Tamanho do efeito (d de Cohen)", true)] },
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (1ª − 2ª)")] },
    { title: "Pressupostos e gráficos", items: [toggle("normalityTest", "Normalidade das diferenças (Shapiro-Wilk)"), toggle("qqPlot", "Gráfico Q-Q das diferenças"), toggle("descriptivesPlot", "Gráfico descritivo")] },
  ],
  derive: (s) => ({ pairs: pairsOf(s) }),
  parseVars: (o) => {
    const ps = Array.isArray(o.pairs) ? (o.pairs as unknown[]).filter(Array.isArray).map((p) => (p as unknown[]).filter((x): x is string => typeof x === "string")) : [];
    return {
      first: ps[0]?.[0] ? [ps[0][0]] : [], second: ps[0]?.[1] ? [ps[0][1]] : [],
      moreFirst: ps.slice(1).map((p) => p[0]).filter(Boolean), moreSecond: ps.slice(1).map((p) => p[1]).filter(Boolean),
    };
  },
  hint: (s) => { const ps = pairsOf(s); return ps.length > 1 ? `Pares formados: ${ps.map(pairLabel).join("; ")}.` : null; },
  check: (ctx) => (!ctx.state.values.student && !ctx.state.values.wilcoxon ? ["Selecione ao menos um teste."] : pairsCheck(ctx)),
};

export const ONESAMPLE_TTEST_DEF: AnalysisDef = {
  id: "TTestOneSample",
  title: "Teste t de uma amostra",
  description: "Compara a média de uma variável escalar com um valor de referência.",
  slots: [{ key: "dependent", label: "Variável (escalar)", levels: ["scale"], multi: true, required: true, min: 1 }],
  sections: [
    { title: "Referência", items: [{ type: "number", key: "testValue", label: "Valor de referência", default: 0, min: -1e12, max: 1e12, step: 0.1 }] },
    {
      title: "Testes",
      items: [
        toggle("student", "Student", true), toggle("wilcoxon", "Wilcoxon"), toggle("zTest", "Teste z (desvio padrão populacional conhecido)"),
        { type: "number", key: "zTestSd", label: "Desvio padrão populacional (σ)", default: 1, min: 1e-6, max: 1e12, step: 0.1, showIf: (v) => !!v.zTest },
      ],
    },
    { title: "Adicionais", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("meanDifference", "Diferença média", true), toggle("effectSize", "Tamanho do efeito (d de Cohen)", true)] },
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (média vs referência)")] },
    { title: "Pressupostos e gráficos", items: [toggle("normalityTest", "Normalidade (Shapiro-Wilk)"), toggle("qqPlot", "Gráfico Q-Q"), toggle("descriptivesPlot", "Gráfico descritivo")] },
  ],
  check: ({ state }) => (!state.values.student && !state.values.wilcoxon && !state.values.zTest ? ["Selecione ao menos um teste."] : []),
};

export const DESCRIPTIVES_DEF: AnalysisDef = {
  id: "Descriptives",
  title: "Estatísticas descritivas",
  description: "Resume variáveis (N, média, desvio padrão, quartis…), opcionalmente separadas pelos níveis de uma variável categórica.",
  slots: [
    { key: "variables", label: "Variáveis", levels: ["scale", "ordinal", "nominal"], multi: true, required: true, min: 1 },
    { key: "splitBy", label: "Separar por (categórica, opcional)", levels: ["nominal", "ordinal"], multi: false, asArray: true },
  ],
  sections: [
    {
      title: "Tendência central e N",
      items: [toggle("valid", "N válido", true), toggle("missing", "Ausentes", true), toggle("meanArithmetic", "Média", true), toggle("median", "Mediana", true), toggle("mode", "Moda"), toggle("sum", "Soma")],
    },
    {
      title: "Dispersão",
      items: [toggle("sd", "Desvio padrão", true), toggle("variance", "Variância"), toggle("seMean", "Erro padrão da média"), toggle("coefficientOfVariation", "Coeficiente de variação"), toggle("iqr", "Amplitude interquartil"), toggle("range", "Amplitude (máx. − mín.)"), toggle("minimum", "Mínimo", true), toggle("maximum", "Máximo", true), toggle("quartiles", "Quartis")],
    },
    {
      title: "Forma e intervalo",
      items: [
        toggle("skewness", "Assimetria"), toggle("kurtosis", "Curtose"), toggle("shapiroWilkTest", "Normalidade (Shapiro-Wilk)"), toggle("meanCi", "Intervalo de confiança da média"),
        { type: "number", key: "meanCiLevel", label: "Nível de confiança", default: 0.95, min: 0.5, max: 0.999, step: 0.01, showIf: (v) => !!v.meanCi },
      ],
    },
    { title: "Tabelas", items: [toggle("frequencyTables", "Tabelas de frequência (variáveis categóricas)")] },
    { title: "Gráficos", items: [toggle("distributionPlots", "Distribuição (histograma)"), toggle("boxPlot", "Boxplot"), toggle("qqPlot", "Gráfico Q-Q")] },
  ],
  check: ({ state }) => {
    const a = state.vars.variables, g = state.vars.splitBy[0];
    return g && a.includes(g) ? [`“${g}” não pode ser analisada e usada para separar ao mesmo tempo.`] : [];
  },
};

export const ANCOVA_DEF: AnalysisDef = {
  id: "Ancova",
  title: "ANCOVA",
  description: "ANOVA ajustada por uma ou mais covariáveis escalares: compara os níveis dos fatores descontando o efeito das covariáveis. Em blocos casualizados, inclua o bloco como fator.",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, required: true, autofill: true },
    { key: "fixedFactors", label: "Fatores (tratamento, bloco…)", levels: ["nominal", "ordinal"], multi: true, required: true, min: 1 },
    { key: "covariates", label: "Covariáveis (escalares)", levels: ["scale"], multi: true, required: true, min: 1 },
  ],
  sections: [
    { title: "Modelo", items: [toggle("interactions", "Incluir interações entre os fatores", false, { local: true })] },
    { title: "Pressupostos", items: [toggle("homogeneityTests", "Homogeneidade de variâncias (Levene)"), toggle("qqPlot", "Gráfico Q-Q dos resíduos")] },
    { title: "Estatísticas", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("effectSizeEtaSquared", "η² (eta ao quadrado)"), toggle("effectSizePartialEtaSquared", "η² parcial"), toggle("effectSizeOmegaSquared", "ω² (ômega ao quadrado)")] },
    {
      title: "Médias ajustadas pela covariável",
      items: [toggle("marginals", "Médias marginais ajustadas de cada fator (covariável na média)", false, { local: true })],
    },
    {
      title: "Comparações múltiplas (médias ajustadas)",
      items: [
        toggle("posthoc", "Comparar os níveis de cada fator dois a dois", false, { local: true }),
        toggle("postHocCorrectionTukey", "Tukey", true, { showIf: (v) => !!v.posthoc }), toggle("postHocCorrectionHolm", "Holm", false, { showIf: (v) => !!v.posthoc }), toggle("postHocCorrectionBonferroni", "Bonferroni", false, { showIf: (v) => !!v.posthoc }),
      ],
    },
  ],
  // Efeitos principais de fatores e covariáveis (as covariáveis entram só como efeito principal) + interações entre fatores, se pedidas.
  derive: (s) => {
    const f = s.vars.fixedFactors;
    const terms = [...f, ...s.vars.covariates].map((x) => ({ components: [x] }));
    if (s.values.interactions) for (const combo of interactionTerms(f)) terms.push({ components: combo });
    const anyEffect = !!(s.values.effectSizeEtaSquared || s.values.effectSizePartialEtaSquared || s.values.effectSizeOmegaSquared);
    return {
      modelTerms: terms, effectSizeEstimates: anyEffect,
      marginalMeanTerms: s.values.marginals ? f : [],
      postHocTerms: s.values.posthoc ? f : [], postHocTypeStandard: !!s.values.posthoc,
    };
  },
  parse: (o) => ({
    interactions: ANOVA_DEF.parse!(o).interactions,
    marginals: Array.isArray(o.marginalMeanTerms) && o.marginalMeanTerms.length > 0,
    posthoc: Array.isArray(o.postHocTerms) && o.postHocTerms.length > 0,
  }),
  check: ANOVA_DEF.check,
};

export const LOGISTIC_DEF: AnalysisDef = {
  id: "RegressionLogistic",
  title: "Regressão logística",
  description: "Modela a chance de um desfecho binário (2 categorias) a partir de covariáveis escalares e fatores. O JASP modela a probabilidade da 2ª categoria (ordem alfabética); a 1ª é a referência.",
  slots: [
    { key: "dependent", label: "Desfecho binário (2 categorias)", levels: ["nominal", "ordinal"], multi: false, required: true, autofill: true, preferLevels: 2 },
    { key: "covariates", label: "Covariáveis (escalares)", levels: ["scale"], multi: true },
    { key: "factors", label: "Fatores (categóricos)", levels: ["nominal", "ordinal"], multi: true },
  ],
  sections: [
    {
      title: "Coeficientes",
      items: [
        toggle("coefficientEstimate", "Estimativas (Wald)", true), toggle("oddsRatio", "Razão de chances (odds ratio)", true), toggle("coefficientCi", "Intervalo de confiança dos coeficientes"),
        { type: "number", key: "coefficientCiLevel", label: "Nível de confiança", default: 0.95, min: 0.5, max: 0.999, step: 0.01, showIf: (v) => !!v.coefficientCi },
        toggle("coefficientCiAsOddsRatio", "Mostrar o intervalo como razão de chances", true, { showIf: (v) => !!v.coefficientCi }),
        toggle("descriptives", "Estatísticas descritivas"),
      ],
    },
    {
      title: "Desempenho do modelo",
      items: [toggle("confusionMatrix", "Matriz de confusão", true), toggle("accuracy", "Acurácia", true), toggle("auc", "AUC", true), toggle("sensitivity", "Sensibilidade"), toggle("specificity", "Especificidade"), toggle("precision", "Precisão")],
    },
    { title: "Diagnóstico e gráficos", items: [toggle("multicollinearity", "Multicolinearidade (VIF)"), toggle("rocPlot", "Curva ROC"), toggle("residualVsFittedPlot", "Resíduos × valores ajustados")] },
    {
      title: "Seleção de preditores",
      items: [{
        type: "choice", key: "method", label: "Método", default: "enter",
        options: [{ value: "enter", label: "Enter (todos os preditores de uma vez)" }, { value: "backward", label: "Backward (parte do modelo cheio e remove por AIC)" }, { value: "forward", label: "Forward (parte do nulo e adiciona por AIC)" }, { value: "stepwise", label: "Stepwise (adiciona e remove por AIC)" }],
      }],
    },
  ],
  // Como na regressão linear, `modelTerms` é uma lista de MODELOS. `enter`: um modelo com todos os preditores. Nos métodos por AIC o
  // JASP só percorre os passos com DOIS blocos: um vazio (preditores "forçados": nenhum) e os candidatos (conferido contra step() do R).
  derive: (s) => {
    const predictors = [...s.vars.covariates, ...s.vars.factors];
    if (predictors.length === 0) return { modelTerms: [] };
    const candidates = { components: predictors, name: "model1", title: "Model 1" };
    return { modelTerms: s.values.method === "enter" || !s.values.method ? [candidates] : [{ components: [], name: "model0", title: "Model 0" }, candidates] };
  },
  hint: (s) => (s.values.method && s.values.method !== "enter" ? "Nos métodos por AIC a tabela mostra cada passo (M₀, M₁…); o último modelo é o selecionado." : null),
  check: ({ dataset, state }) => {
    const out: string[] = [];
    const y = state.vars.dependent[0];
    const n = y ? colOf(dataset, y)?.n_distinct ?? null : null;
    if (n !== null && n !== 2) out.push(`${y} tem ${levelsLabel(n)}, e a regressão logística precisa de um desfecho com exatamente 2 categorias. Escolha outra variável ou crie uma com SQL (ex.: CASE WHEN … THEN 'alto' ELSE 'baixo' END) e “Salvar como dataset”.`);
    if (state.vars.covariates.length + state.vars.factors.length === 0) out.push("Escolha ao menos uma covariável ou um fator.");
    return out;
  },
};

// ------------------------------------------------------------------------------------------------------------------
// Versões bayesianas (fatia 6.6). Fator de Bayes com prior de Cauchy sobre o tamanho do efeito (testes t) ou sobre os
// efeitos fixos (ANOVA). Valores conferidos contra o pacote BayesFactor nos testes de integração.
const bfType = (): Item => ({
  type: "choice", key: "bayesFactorType", label: "Fator de Bayes", default: "BF10",
  options: [{ value: "BF10", label: "BF₁₀ (evidência para H₁ contra H₀)" }, { value: "BF01", label: "BF₀₁ (evidência para H₀ contra H₁)" }, { value: "LogBF10", label: "log(BF₁₀)" }],
});
const cauchyWidth = (key: string, label: string, def: number): Item => ({ type: "number", key, label, default: def, min: 0.05, max: 2, step: 0.01 });
const BAYES_T_PRIOR = { title: "Prior (Cauchy sobre o tamanho do efeito)", items: [cauchyWidth("priorWidth", "Largura do prior (0,707 = “médio”)", 0.707)] };
const BAYES_T_PLOTS = { title: "Gráficos", items: [toggle("priorAndPosteriorPlot", "Prior e posterior"), toggle("bfRobustnessPlot", "Robustez do fator de Bayes à largura do prior")] };

export const BAYES_TTEST_DEF: AnalysisDef = {
  id: "TTestBayesianIndependentSamples",
  title: "Teste t independente bayesiano",
  description: "Fator de Bayes para a diferença de médias entre dois grupos: quanto os dados favorecem “há diferença” (H₁) contra “não há” (H₀).",
  slots: TTEST_DEF.slots,
  sections: [
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (grupo 1 vs grupo 2)")] },
    BAYES_T_PRIOR,
    { title: "Resultado", items: [bfType(), toggle("descriptives", "Estatísticas descritivas", true), toggle("descriptivesPlot", "Gráfico descritivo")] },
    BAYES_T_PLOTS,
  ],
  check: ({ dataset, state }) => {
    const g = state.vars.group[0];
    const n = g ? colOf(dataset, g)?.n_distinct ?? null : null;
    return n !== null && n !== 2 ? [`${g} tem ${levelsLabel(n)}, e o teste t compara exatamente 2 grupos. Escolha outra variável ou filtre os dados (aba Consulta SQL).`] : [];
  },
};

export const BAYES_PAIRED_TTEST_DEF: AnalysisDef = {
  id: "TTestBayesianPairedSamples",
  title: "Teste t pareado bayesiano",
  description: "Fator de Bayes para a diferença entre duas medidas da mesma unidade (antes/depois).",
  slots: PAIRED_TTEST_DEF.slots,
  sections: [
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (1ª − 2ª)")] },
    BAYES_T_PRIOR,
    { title: "Resultado", items: [bfType(), toggle("descriptives", "Estatísticas descritivas", true), toggle("descriptivesPlot", "Gráfico descritivo")] },
    BAYES_T_PLOTS,
  ],
  derive: PAIRED_TTEST_DEF.derive,
  parseVars: PAIRED_TTEST_DEF.parseVars,
  hint: PAIRED_TTEST_DEF.hint,
  check: pairsCheck,
};

export const BAYES_ONESAMPLE_TTEST_DEF: AnalysisDef = {
  id: "TTestBayesianOneSample",
  title: "Teste t de uma amostra bayesiano",
  description: "Fator de Bayes para a média de uma variável contra um valor de referência.",
  slots: ONESAMPLE_TTEST_DEF.slots,
  sections: [
    { title: "Referência", items: [{ type: "number", key: "testValue", label: "Valor de referência", default: 0, min: -1e12, max: 1e12, step: 0.1 }] },
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (média vs referência)")] },
    BAYES_T_PRIOR,
    { title: "Resultado", items: [bfType(), toggle("descriptives", "Estatísticas descritivas", true), toggle("descriptivesPlot", "Gráfico descritivo")] },
    BAYES_T_PLOTS,
  ],
};

export const BAYES_ANOVA_DEF: AnalysisDef = {
  id: "AnovaBayesian",
  title: "ANOVA bayesiana",
  description: "Compara modelos (nulo, cada fator, combinações) pelo fator de Bayes e mede a evidência de cada efeito. Em blocos casualizados, inclua o bloco como fator.",
  slots: ANOVA_DEF.slots,
  sections: [
    { title: "Modelo", items: [toggle("interactions", "Incluir interações entre os fatores", false, { local: true })] },
    { title: "Prior (Cauchy sobre os efeitos fixos)", items: [cauchyWidth("cauchyPriorScaleFixedEffects", "Largura do prior (r)", 0.5)] },
    {
      title: "Resultado",
      items: [
        bfType(),
        { type: "choice", key: "bayesFactorOrder", label: "Comparar com", default: "bestModelTop", options: [{ value: "bestModelTop", label: "o melhor modelo" }, { value: "nullModelTop", label: "o modelo nulo" }] },
        toggle("effects", "Evidência de cada efeito (BF de inclusão)", true),
        { type: "choice", key: "effectsType", label: "Inclusão calculada sobre", default: "allModels", showIf: (v) => !!v.effects, options: [{ value: "allModels", label: "todos os modelos" }, { value: "matchedModels", label: "modelos equivalentes (matched)" }] },
        toggle("descriptives", "Estatísticas descritivas"),
        toggle("posteriorEstimates", "Estimativas a posteriori (média e IC credível)"),
      ],
    },
  ],
  // Resultados reproduzíveis: a ANOVA bayesiana usa amostragem de Monte Carlo; fixamos a semente (o JASP, por padrão, não fixa).
  derive: (s) => {
    const f = s.vars.fixedFactors;
    const terms = f.map((x) => ({ components: [x] }));
    if (s.values.interactions) for (const combo of interactionTerms(f)) terms.push({ components: combo });
    return { modelTerms: terms, setSeed: true, seed: 1 };
  },
  parse: (o) => ({ interactions: ANOVA_DEF.parse!(o).interactions }),
  check: ANOVA_DEF.check,
};

// ------------------------------------------------------------------------------------------------------------------
// Testes z (fatia 6.12). ATENÇÃO: não existem no JASP instalado, então são calculados pelo motor da plataforma em R base
// (engines/r-worker/custom.R), com a saída no mesmo formato; cada tabela traz uma nota dizendo isso. O teste z de UMA média
// (σ conhecido) é do JASP (opção `zTest` do t de uma amostra). Fórmulas conferidas contra pnorm/prop.test nos testes.
const ciLevel = (): Item => ({ type: "number", key: "ciLevel", label: "Nível de confiança do IC", default: 0.95, min: 0.5, max: 0.9999, step: 0.01 });
const twoLevels = (dataset: Dataset, name: string | undefined, what: string): string[] => {
  const n = name ? colOf(dataset, name)?.n_distinct ?? null : null;
  return n !== null && n !== 2 ? [`${name} tem ${levelsLabel(n)}; ${what} exige exatamente 2 categorias. Escolha outra variável ou filtre os dados (aba Consulta SQL).`] : [];
};

export const ZTEST_MEANS_DEF: AnalysisDef = {
  id: "ZTestMeans",
  title: "Teste z de duas amostras (σ conhecidos)",
  description: "Compara a média de dois grupos quando os desvios padrão POPULACIONAIS são conhecidos (z = (m₁ − m₂)/√(σ₁²/n₁ + σ₂²/n₂)). Se σ é estimado pela amostra, use o teste t. Calculado pela plataforma (R base), não por um módulo JASP.",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, required: true, autofill: true },
    { key: "group", label: "Variável de agrupamento (2 grupos)", levels: ["nominal", "ordinal"], multi: false, required: true, autofill: true, preferLevels: 2 },
  ],
  sections: [
    {
      title: "Desvios padrão populacionais (conhecidos)",
      items: [
        { type: "number", key: "sigma1", label: "σ do 1º grupo (ordem alfabética)", default: 1, min: 1e-6, max: 1e9, step: 0.1 },
        { type: "number", key: "sigma2", label: "σ do 2º grupo", default: 1, min: 1e-6, max: 1e9, step: 0.1 },
      ],
    },
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (1º grupo vs 2º)")] },
    { title: "Resultado", items: [ciLevel(), toggle("descriptives", "Estatísticas descritivas", true)] },
  ],
  check: ({ dataset, state }) => twoLevels(dataset, state.vars.group[0], "o teste z compara dois grupos e"),
};

export const ZTEST_PROPORTIONS_DEF: AnalysisDef = {
  id: "ZTestProportions",
  title: "Teste z de proporções",
  description: "Sem grupo: compara a proporção de “sucesso” com um valor p₀ (uma amostra). Com grupo de 2 níveis: compara as proporções dos dois grupos (duas amostras). Sucesso = a 2ª categoria do desfecho em ordem alfabética. Calculado pela plataforma (R base), não por um módulo JASP.",
  slots: [
    { key: "outcome", label: "Desfecho (2 categorias)", levels: ["nominal", "ordinal"], multi: false, required: true, autofill: true, preferLevels: 2 },
    { key: "group", label: "Grupos (2 níveis; vazio = uma amostra)", levels: ["nominal", "ordinal"], multi: false, preferLevels: 2 },
  ],
  sections: [
    { title: "Sucesso", items: [toggle("invert", "Sucesso = a 1ª categoria (padrão: a 2ª, em ordem alfabética)")] },
    { title: "Uma amostra", items: [{ type: "number", key: "p0", label: "p₀ (valor de referência; só sem grupo)", default: 0.5, min: 0.001, max: 0.999, step: 0.01 }] },
    { title: "Hipótese alternativa", items: [alternative("Hipótese alternativa (proporção vs p₀, ou 1º grupo vs 2º)")] },
    { title: "Resultado", items: [ciLevel()] },
  ],
  check: ({ dataset, state }) => {
    const out = state.vars.outcome[0], grp = state.vars.group[0];
    const msgs = twoLevels(dataset, out, "o teste de proporções (desfecho)");
    if (grp) msgs.push(...twoLevels(dataset, grp, "o teste de duas proporções (grupos)"));
    if (out && out === grp) msgs.push("O desfecho e o grupo não podem ser a mesma variável.");
    return msgs;
  },
};

// ------------------------------------------------------------------------------------------------------------------
// ANOVA de medidas repetidas (fatia 6.9): UM fator intra-sujeito. Os níveis são colunas do dataset (formato largo: uma
// coluna por medida, na ordem em que o usuário as marca); o nome do fator é livre. Fatores entre-sujeitos opcionais.
export const RM_ANOVA_DEF: AnalysisDef = {
  id: "AnovaRepeatedMeasures",
  title: "ANOVA de medidas repetidas",
  description: "Compara as médias de uma mesma unidade medida várias vezes (tempos, condições). Cada medida é uma coluna: marque-as na ordem. Fatores entre-sujeitos (grupos) são opcionais e dão um delineamento misto.",
  slots: [
    { key: "repeatedMeasuresCells", label: "Medidas repetidas (colunas, na ordem dos níveis)", levels: ["scale"], multi: true, required: true, min: 2, ordered: true },
    { key: "betweenSubjectFactors", label: "Fatores entre-sujeitos (grupos, opcional)", levels: ["nominal", "ordinal"], multi: true },
  ],
  sections: [
    { title: "Fator intra-sujeito", items: [{ type: "text", key: "factorName", label: "Nome do fator (ex.: tempo)", default: "tempo", maxLength: 40, local: true }] },
    {
      title: "Esfericidade",
      items: [toggle("sphericityTests", "Teste de esfericidade (Mauchly)", true), toggle("sphericityCorrectionNone", "Sem correção", true), toggle("sphericityCorrectionGreenhouseGeisser", "Greenhouse-Geisser", true), toggle("sphericityCorrectionHuynhFeldt", "Huynh-Feldt")],
    },
    { title: "Estatísticas", items: [toggle("descriptives", "Estatísticas descritivas", true), toggle("effectSizePartialEtaSquared", "η² parcial"), toggle("effectSizeGeneralEtaSquared", "η² generalizado"), toggle("effectSizeOmegaSquared", "ω² (ômega ao quadrado)")] },
    {
      title: "Comparações múltiplas entre os níveis do fator intra",
      items: [toggle("posthoc", "Comparar os níveis dois a dois", false, { local: true }), toggle("postHocCorrectionHolm", "Holm", true, { showIf: (v) => !!v.posthoc }), toggle("postHocCorrectionBonferroni", "Bonferroni", false, { showIf: (v) => !!v.posthoc })],
    },
    {
      title: "Não paramétrico (um teste só, com todos os sujeitos)",
      items: [
        toggle("friedman", "Teste de Friedman (alternativa à ANOVA; ignora os grupos)", false, { local: true }),
        toggle("conover", "Post hoc de Conover (Bonferroni e Holm)", false, { local: true, showIf: (v) => !!v.friedman }),
      ],
    },
  ],
  derive: (s) => {
    const name = String(s.values.factorName ?? "").trim();
    const between = s.vars.betweenSubjectFactors;
    const anyEffect = !!(s.values.effectSizePartialEtaSquared || s.values.effectSizeGeneralEtaSquared || s.values.effectSizeOmegaSquared);
    return {
      repeatedMeasuresFactors: [{ name, levels: s.vars.repeatedMeasuresCells }],
      withinModelTerms: [{ components: [name] }],
      betweenModelTerms: between.map((b) => ({ components: [b] })),
      effectSizeEstimates: anyEffect,
      postHocTerms: s.values.posthoc ? [name] : [],
      // Friedman com fator de agrupamento do JASP devolveria NaN no Conover: por isso o teste vale para todos os sujeitos juntos
      friedmanWithinFactor: s.values.friedman ? [name] : [],
      conoverTest: !!(s.values.friedman && s.values.conover),
    };
  },
  parse: (o) => {
    const f = Array.isArray(o.repeatedMeasuresFactors) ? (o.repeatedMeasuresFactors[0] as { name?: unknown } | undefined) : undefined;
    return {
      factorName: typeof f?.name === "string" ? f.name : "tempo",
      posthoc: Array.isArray(o.postHocTerms) && o.postHocTerms.length > 0,
      friedman: Array.isArray(o.friedmanWithinFactor) && o.friedmanWithinFactor.length > 0,
      conover: o.conoverTest === true,
    };
  },
  check: ({ state }) => {
    const name = String(state.values.factorName ?? "").trim();
    const out: string[] = [];
    if (name === "") out.push("Dê um nome ao fator intra-sujeito (ex.: tempo).");
    else if (state.vars.repeatedMeasuresCells.includes(name) || state.vars.betweenSubjectFactors.includes(name)) out.push(`O nome do fator (“${name}”) não pode ser igual ao de uma coluna escolhida.`);
    return out;
  },
};

// Bayesianas da 6.15: correlação (prior beta esticado), regressão linear (JZS), ANCOVA e qui-quadrado (Dirichlet/Poisson).
export const BAYES_CORRELATION_DEF: AnalysisDef = {
  id: "CorrelationBayesian",
  title: "Correlação bayesiana",
  description: "Fator de Bayes para a correlação de Pearson entre pares de variáveis: quanto os dados favorecem “há correlação” (H₁) contra “não há” (H₀, ρ = 0).",
  slots: CORRELATION_DEF.slots,
  sections: [
    {
      title: "Hipótese alternativa",
      items: [{ type: "choice", key: "alternative", label: "Hipótese alternativa", default: "twoSided", options: [{ value: "twoSided", label: "Bilateral (ρ ≠ 0)" }, { value: "greater", label: "Positiva (ρ > 0)" }, { value: "less", label: "Negativa (ρ < 0)" }] }],
    },
    { title: "Prior (beta esticado sobre ρ)", items: [{ type: "number", key: "priorWidth", label: "Largura κ do prior (1 = uniforme em −1…1)", default: 1, min: 0.05, max: 3, step: 0.05 }] },
    { title: "Resultado", items: [bfType(), toggle("ci", "Intervalo credível (95%) de ρ"), toggle("sampleSize", "N de cada par")] },
  ],
};

export const BAYES_REGRESSION_DEF: AnalysisDef = {
  id: "RegressionLinearBayesian",
  title: "Regressão linear bayesiana",
  description: "Compara todos os modelos possíveis com as covariáveis escolhidas (e o modelo nulo) pelo fator de Bayes, com o prior JZS sobre os coeficientes.",
  slots: [
    { key: "dependent", label: "Variável dependente (escalar)", levels: ["scale"], multi: false, required: true, autofill: true },
    { key: "covariates", label: "Covariáveis (escalares)", levels: ["scale"], multi: true, required: true, min: 1 },
  ],
  sections: [
    { title: "Prior (JZS sobre os coeficientes)", items: [{ type: "number", key: "jzsRScale", label: "Largura do prior (r; 0,354 = padrão)", default: 0.354, min: 0.05, max: 2, step: 0.01 }] },
    {
      title: "Resultado",
      items: [
        bfType(),
        { type: "choice", key: "bayesFactorOrder", label: "Comparar com", default: "bestModelTop", options: [{ value: "bestModelTop", label: "o melhor modelo" }, { value: "nullModelTop", label: "o modelo nulo" }] },
        toggle("posteriorSummaryTable", "Estimativas a posteriori (média e IC credível)"),
        toggle("descriptives", "Estatísticas descritivas"),
      ],
    },
  ],
  // um termo por covariável (efeito principal); semente fixa: com muitos preditores o JASP amostra modelos (BAS) e sem semente o resultado mudaria a cada execução
  derive: (s) => ({ modelTerms: s.vars.covariates.map((c) => ({ components: [c], isNuisance: false })), setSeed: true, seed: 1 }),
};

export const BAYES_ANCOVA_DEF: AnalysisDef = {
  id: "AncovaBayesian",
  title: "ANCOVA bayesiana",
  description: "Compara modelos (nulo, fatores, covariáveis e combinações) pelo fator de Bayes, ajustando por covariáveis escalares. Em blocos casualizados, inclua o bloco como fator.",
  slots: ANCOVA_DEF.slots,
  sections: [
    { title: "Modelo", items: [toggle("interactions", "Incluir interações entre os fatores", false, { local: true })] },
    {
      title: "Prior (Cauchy)",
      items: [cauchyWidth("cauchyPriorScaleFixedEffects", "Largura para os fatores (r)", 0.5), cauchyWidth("cauchyPriorScaleCovariates", "Largura para as covariáveis (r)", 0.354)],
    },
    {
      title: "Resultado",
      items: [
        bfType(),
        { type: "choice", key: "bayesFactorOrder", label: "Comparar com", default: "bestModelTop", options: [{ value: "bestModelTop", label: "o melhor modelo" }, { value: "nullModelTop", label: "o modelo nulo" }] },
        toggle("effects", "Evidência de cada efeito (BF de inclusão)", true),
        { type: "choice", key: "effectsType", label: "Inclusão calculada sobre", default: "allModels", showIf: (v) => !!v.effects, options: [{ value: "allModels", label: "todos os modelos" }, { value: "matchedModels", label: "modelos equivalentes (matched)" }] },
        toggle("descriptives", "Estatísticas descritivas"),
      ],
    },
  ],
  derive: (s) => {
    const f = s.vars.fixedFactors;
    const terms = [...f, ...s.vars.covariates].map((x) => ({ components: [x] }));
    if (s.values.interactions) for (const combo of interactionTerms(f)) terms.push({ components: combo });
    return { modelTerms: terms, setSeed: true, seed: 1 };
  },
  parse: (o) => ({ interactions: ANOVA_DEF.parse!(o).interactions }),
  check: ANOVA_DEF.check,
};

export const BAYES_CONTINGENCY_DEF: AnalysisDef = {
  id: "ContingencyTablesBayesian",
  title: "Qui-quadrado bayesiano (tabela de contingência)",
  description: "Fator de Bayes para a associação entre duas variáveis categóricas (H₁: dependentes; H₀: independentes). Escolha o modelo amostral que descreve como os dados foram coletados.",
  slots: CONTINGENCY_DEF.slots,
  sections: [
    {
      title: "Modelo amostral",
      items: [{
        type: "choice", key: "samplingModel", label: "Como os dados foram coletados", default: "independentMultinomialRowsFixed",
        options: [
          { value: "independentMultinomialRowsFixed", label: "Totais das linhas fixos (ex.: tamanhos dos grupos definidos)" },
          { value: "independentMultinomialColumnsFixed", label: "Totais das colunas fixos" },
          { value: "jointMultinomial", label: "Total geral fixo (N definido, nada mais)" },
          { value: "poisson", label: "Nada fixo (contagens de Poisson)" },
        ],
      }],
    },
    { title: "Prior", items: [{ type: "number", key: "priorConcentration", label: "Concentração do prior (1 = uniforme)", default: 1, min: 0.01, max: 100, step: 0.1 }] },
    { title: "Resultado", items: [bfType()] },
    { title: "Tabela", items: [toggle("countsObserved", "Contagens observadas", true), toggle("countsExpected", "Contagens esperadas"), toggle("percentagesRow", "% nas linhas"), toggle("percentagesColumn", "% nas colunas")] },
  ],
  check: CONTINGENCY_DEF.check,
};

export const ANALYSES: AnalysisDef[] = [TTEST_DEF, PAIRED_TTEST_DEF, ONESAMPLE_TTEST_DEF, ANOVA_DEF, ANCOVA_DEF, RM_ANOVA_DEF, ZTEST_MEANS_DEF, ZTEST_PROPORTIONS_DEF, CORRELATION_DEF, REGRESSION_DEF, LOGISTIC_DEF, CONTINGENCY_DEF, DESCRIPTIVES_DEF, BAYES_TTEST_DEF, BAYES_PAIRED_TTEST_DEF, BAYES_ONESAMPLE_TTEST_DEF, BAYES_ANOVA_DEF, BAYES_ANCOVA_DEF, BAYES_CORRELATION_DEF, BAYES_REGRESSION_DEF, BAYES_CONTINGENCY_DEF];
export const getDef = (id: string): AnalysisDef | undefined => ANALYSES.find((d) => d.id === id);

/** Como o seletor agrupa as análises (aba Análise e bloco de relatório). Cada análise do catálogo está em exatamente um grupo. */
export const ANALYSIS_GROUPS: { title: string; ids: string[] }[] = [
  { title: "Descritivas", ids: ["Descriptives"] },
  { title: "Comparação de médias", ids: ["TTestIndependentSamples", "TTestPairedSamples", "TTestOneSample", "Anova", "Ancova", "AnovaRepeatedMeasures"] },
  { title: "Testes z (σ conhecido e proporções)", ids: ["ZTestMeans", "ZTestProportions"] },
  { title: "Associação e predição", ids: ["Correlation", "RegressionLinear", "RegressionLogistic", "ContingencyTables"] },
  { title: "Bayesianas", ids: ["TTestBayesianIndependentSamples", "TTestBayesianPairedSamples", "TTestBayesianOneSample", "AnovaBayesian", "AncovaBayesian", "CorrelationBayesian", "RegressionLinearBayesian", "ContingencyTablesBayesian"] },
];
export const groupedAnalyses = (): { title: string; defs: AnalysisDef[] }[] =>
  ANALYSIS_GROUPS.map((g) => ({ title: g.title, defs: g.ids.map((id) => getDef(id)).filter((d): d is AnalysisDef => !!d) }));


// ------------------------------------------------------------------------------------------------------------------
const allItems = (def: AnalysisDef) => def.sections.flatMap((s) => s.items);

export function defaultState(def: AnalysisDef): FormState {
  return {
    vars: Object.fromEntries(def.slots.map((s) => [s.key, []])),
    values: Object.fromEntries(allItems(def).map((i) => [i.key, i.default])),
  };
}

/** Colunas que podem ocupar o campo, em ordem de preferência. */
const NUMERIC_DTYPES = new Set(["TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "FLOAT", "DOUBLE", "REAL", "DECIMAL"]);
export const isNumericDtype = (dtype: string) => NUMERIC_DTYPES.has(dtype.split("(")[0].toUpperCase());

/**
 * Ordinal NUMÉRICA (escala Likert 1–5, inteiros com poucos valores distintos) num campo que pede variável ESCALAR.
 * Vale: o JASP lê cada variável pelo papel que ela tem na análise (conferido contra o R em testes de integração), então
 * a coluna não precisa virar "escalar" na aba Dados. Ordinal de texto (rótulos) continua fora.
 */
export const ordinalAsScale = (slot: VarSlot, c: Column) =>
  c.measurement === "ordinal" && isNumericDtype(c.dtype) && slot.levels.includes("scale") && !slot.levels.includes("ordinal");

export function candidates(slot: VarSlot, dataset: Dataset | undefined): Column[] {
  // as genuinamente do nível pedido vêm primeiro (o preenchimento automático não escolhe uma Likert antes de uma escalar)
  const cols = (dataset?.columns ?? []).filter((c) => slot.levels.includes(c.measurement) || ordinalAsScale(slot, c));
  const rank = (c: Column) => Number(ordinalAsScale(slot, c));
  const sorted = [...cols].sort((a, b) => rank(a) - rank(b));
  if (slot.preferLevels === undefined) return sorted;
  return sorted.sort((a, b) => Number(b.n_distinct === slot.preferLevels) - Number(a.n_distinct === slot.preferLevels));
}

/**
 * Estado efetivo: descarta o que não existe mais (coluna removida ou nível de medida alterado), limita campos únicos a uma
 * coluna, completa campos únicos obrigatórios com o primeiro candidato livre e garante valor de tipo certo em cada opção.
 */
export function resolveState(def: AnalysisDef, dataset: Dataset | undefined, state: FormState): FormState {
  const vars: Record<string, string[]> = {};
  const used = new Set<string>();
  for (const slot of def.slots) {
    const cands = candidates(slot, dataset);
    const ok = new Set(cands.map((c) => c.name));
    let chosen = [...new Set(state.vars[slot.key] ?? [])].filter((n) => ok.has(n));
    if (!slot.multi) chosen = chosen.slice(0, 1);
    if (!slot.multi && slot.required && slot.autofill && chosen.length === 0) {
      const free = cands.find((c) => !used.has(c.name));
      if (free) chosen = [free.name];
    }
    vars[slot.key] = chosen;
    chosen.forEach((n) => used.add(n));
  }
  const values: Values = {};
  for (const item of allItems(def)) {
    const v = state.values[item.key];
    const typeOk = item.type === "toggle" ? typeof v === "boolean"
      : item.type === "number" ? typeof v === "number" && Number.isFinite(v)
      : item.type === "text" ? typeof v === "string" && v.length <= item.maxLength
      : item.options.some((o) => o.value === v);
    values[item.key] = typeOk ? v : item.default;
  }
  return { vars, values };
}

/** Motivos pelos quais a análise ainda não pode ser executada (lista vazia = pode). Espera um estado já resolvido. */
export function problems(def: AnalysisDef, dataset: Dataset | undefined, state: FormState): string[] {
  const out: string[] = [];
  if (!dataset) return ["Escolha um dataset."];
  for (const slot of def.slots) {
    const chosen = state.vars[slot.key] ?? [];
    const label = slot.label.replace(/\s*\(.*\)\s*$/, "");
    if (slot.required && chosen.length === 0) {
      out.push(candidates(slot, dataset).length === 0
        ? `Nenhuma coluna ${slot.levels.map((l) => MEASURE_NAME[l]).join(" ou ")} disponível para “${label}”. Ajuste o nível de medida na aba Dados.`
        : `Escolha ${label.toLowerCase()}.`);
    } else if (slot.multi && slot.min && chosen.length > 0 && chosen.length < slot.min) {
      out.push(`Escolha ao menos ${slot.min} em “${label}”.`);
    }
  }
  const seen = new Map<string, string>();
  for (const slot of def.slots) {
    if (slot.shared) continue;
    for (const name of state.vars[slot.key] ?? []) {
      if (seen.has(name) && seen.get(name) !== slot.key) out.push(`“${name}” está em mais de um campo.`);
      seen.set(name, slot.key);
    }
  }
  if (out.length === 0) out.push(...(def.check?.({ dataset, state }) ?? []));
  return out;
}

/** Estado -> opções do JASP (o que a API/relatório guarda e envia ao motor). */
export function toOptions(def: AnalysisDef, state: FormState): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  for (const slot of def.slots) {
    if (slot.local) continue;
    const v = state.vars[slot.key] ?? [];
    o[slot.key] = slot.multi || slot.asArray ? v : v[0] ?? "";
  }
  for (const item of allItems(def)) if (!item.local) o[item.key] = state.values[item.key] ?? item.default;
  return { ...o, ...def.derive?.(state) };
}

/** Opções salvas -> estado do formulário (campos ausentes ou de tipo errado usam o padrão). */
export function fromOptions(def: AnalysisDef, options: Record<string, unknown>): FormState {
  const base = defaultState(def);
  for (const slot of def.slots) {
    if (slot.local) continue;
    const raw = options[slot.key];
    const arr = Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string" && x !== "") : typeof raw === "string" && raw ? [raw] : [];
    base.vars[slot.key] = arr;
  }
  for (const item of allItems(def)) if (!item.local && typeof options[item.key] === typeof item.default) base.values[item.key] = options[item.key] as boolean | number | string;
  Object.assign(base.values, def.parse?.(options));
  Object.assign(base.vars, def.parseVars?.(options));
  return base;
}

/** Os campos obrigatórios estão preenchidos? (não precisa do dataset: usado para mostrar o bloco no relatório) */
export function isComplete(def: AnalysisDef, options: Record<string, unknown>): boolean {
  const s = fromOptions(def, options);
  return def.slots.every((slot) => (!slot.required || s.vars[slot.key].length > 0) && (!slot.min || s.vars[slot.key].length >= slot.min));
}

/** O que o usuário fez na aba: vive no App (por dataset) para sobreviver à troca de aba Dados/SQL/Análise. */
export type AnalysisSession = {
  defId: string;
  states: Record<string, FormState>; // cada análise guarda o que o usuário escolheu
  submitted: { analysis: string; options: Record<string, unknown> } | null;
};
export const newSession = (): AnalysisSession => ({ defId: ANALYSES[0].id, states: {}, submitted: null });
