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
}

interface ItemBase { key: string; label: string; local?: boolean; showIf?: (v: Values) => boolean }
export interface ToggleItem extends ItemBase { type: "toggle"; default: boolean }
export interface NumberItem extends ItemBase { type: "number"; default: number; min: number; max: number; step: number }
export interface ChoiceItem extends ItemBase { type: "choice"; default: string; options: { value: string; label: string }[] }
/** `local`: valor só da interface (não vai ao JASP; é usado por `derive`). */
export type Item = ToggleItem | NumberItem | ChoiceItem;

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
  ],
  derive: (s) => {
    const f = s.vars.fixedFactors;
    const terms = f.map((x) => ({ components: [x] }));
    if (s.values.interactions) for (const combo of interactionTerms(f)) terms.push({ components: combo });
    const anyEffect = !!(s.values.effectSizeEtaSquared || s.values.effectSizePartialEtaSquared || s.values.effectSizeOmegaSquared);
    const anyPostHoc = !!(s.values.postHocCorrectionTukey || s.values.postHocCorrectionBonferroni || s.values.postHocCorrectionHolm);
    return { modelTerms: terms, effectSizeEstimates: anyEffect, postHocTerms: anyPostHoc ? f : [] };
  },
  parse: (o) => {
    const terms = Array.isArray(o.modelTerms) ? (o.modelTerms as { components?: unknown[] }[]) : [];
    return { interactions: terms.some((t) => Array.isArray(t.components) && t.components.length > 1) };
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

export const ANALYSES: AnalysisDef[] = [TTEST_DEF, ANOVA_DEF, CORRELATION_DEF, REGRESSION_DEF, CONTINGENCY_DEF];
export const getDef = (id: string): AnalysisDef | undefined => ANALYSES.find((d) => d.id === id);

// ------------------------------------------------------------------------------------------------------------------
const allItems = (def: AnalysisDef) => def.sections.flatMap((s) => s.items);

export function defaultState(def: AnalysisDef): FormState {
  return {
    vars: Object.fromEntries(def.slots.map((s) => [s.key, []])),
    values: Object.fromEntries(allItems(def).map((i) => [i.key, i.default])),
  };
}

/** Colunas que podem ocupar o campo, em ordem de preferência. */
export function candidates(slot: VarSlot, dataset: Dataset | undefined): Column[] {
  const cols = (dataset?.columns ?? []).filter((c) => slot.levels.includes(c.measurement));
  if (slot.preferLevels === undefined) return cols;
  return [...cols].sort((a, b) => Number(b.n_distinct === slot.preferLevels) - Number(a.n_distinct === slot.preferLevels));
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
    const typeOk = item.type === "toggle" ? typeof v === "boolean" : item.type === "number" ? typeof v === "number" && Number.isFinite(v) : item.options.some((o) => o.value === v);
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
    const raw = options[slot.key];
    const arr = Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string" && x !== "") : typeof raw === "string" && raw ? [raw] : [];
    base.vars[slot.key] = arr;
  }
  for (const item of allItems(def)) if (!item.local && typeof options[item.key] === typeof item.default) base.values[item.key] = options[item.key] as boolean | number | string;
  Object.assign(base.values, def.parse?.(options));
  return base;
}

/** Os campos obrigatórios estão preenchidos? (não precisa do dataset: usado para mostrar o bloco no relatório) */
export function isComplete(def: AnalysisDef, options: Record<string, unknown>): boolean {
  const s = fromOptions(def, options);
  return def.slots.every((slot) => (!slot.required || s.vars[slot.key].length > 0) && (!slot.min || s.vars[slot.key].length >= slot.min));
}
