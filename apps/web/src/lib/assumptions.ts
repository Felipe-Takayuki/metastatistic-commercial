/**
 * Verificação automática de pressupostos. Depois de uma análise, a interface pede ao motor, em segundo plano, as mesmas
 * opções MAIS os testes de pressuposto (Shapiro-Wilk, Levene), lê as tabelas e mostra avisos em português. O usuário não
 * precisa marcar nada, e a saída que ele pediu não ganha tabelas que ele não pediu.
 */

/** Opções do JASP que ligam os testes de pressuposto de cada análise. */
const CHECKS: Record<string, Record<string, boolean>> = {
  TTestIndependentSamples: { normalityTest: true, equalityOfVariancesTest: true },
  TTestPairedSamples: { normalityTest: true },
  TTestOneSample: { normalityTest: true },
  Anova: { homogeneityTests: true },
  Ancova: { homogeneityTests: true },
};

export const ALPHA = 0.05;

export interface Note { level: "warn" | "ok"; text: string }

/** As opções da análise acrescidas dos testes de pressuposto; `null` se a análise não tem pressupostos verificáveis. */
export function assumptionOptions(analysis: string, options: Record<string, unknown>): Record<string, unknown> | null {
  const extra = CHECKS[analysis];
  return extra ? { ...options, ...extra } : null;
}

type Row = Record<string, unknown>;

/** Todas as tabelas (`{schema, data}`) da árvore de resultados cujo caminho termina em `suffix`. */
function tablesEndingWith(node: unknown, suffix: string, path = ""): Row[][] {
  if (!node || typeof node !== "object") return [];
  const o = node as Record<string, unknown>;
  const out: Row[][] = [];
  if (o.schema && typeof o.schema === "object" && Array.isArray(o.data) && path.endsWith(suffix)) out.push(o.data as Row[]);
  for (const [k, v] of Object.entries(o)) if (k !== "schema" && k !== "data" && k !== ".meta" && k !== "footnotes") out.push(...tablesEndingWith(v, suffix, `${path}/${k}`));
  return out;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
/** p no estilo APA: sem zero à esquerda, "< .001" para valores muito pequenos. */
export const fmtP = (p: number) => (p < 0.001 ? "p < ,001" : `p = ${p.toFixed(3).replace(/^0/, "").replace(".", ",")}`);
const fmtStat = (x: number) => x.toFixed(2).replace(".", ",");

/** Nome da variável de uma linha da tabela de normalidade: `dep` (independente: o JASP testa os resíduos), `v` (uma amostra), `v1 - v2` (pareado, normalidade das diferenças). */
function normalityName(r: Row): string {
  if (typeof r.dep === "string") return `${r.dep} (resíduos)`;
  if (typeof r.v1 === "string" && typeof r.v2 === "string") return `${r.v1} − ${r.v2} (diferenças)`;
  return typeof r.v === "string" ? r.v : "a variável";
}

const NORMALITY_ADVICE: Record<string, string> = {
  TTestIndependentSamples: "Considere o teste de Mann-Whitney.",
  TTestPairedSamples: "Considere o teste de Wilcoxon (marque-o nos testes).",
  TTestOneSample: "Considere o teste de Wilcoxon (marque-o nos testes).",
};

/** Avisos a partir dos resultados de `assumptionOptions`. Lista vazia = não foi possível verificar nada (tabelas ausentes). */
export function assumptionNotes(analysis: string, results: unknown): Note[] {
  const warn: Note[] = [];
  let checked = 0;

  for (const rows of tablesEndingWith(results, "ttestNormalTable")) {
    for (const r of rows) {
      const p = num(r.p), w = num(r.W);
      if (p === null) continue;
      checked++;
      if (p < ALPHA) warn.push({ level: "warn", text: `Normalidade rejeitada para ${normalityName(r)} (Shapiro-Wilk${w !== null ? `, W = ${fmtStat(w)}` : ""}, ${fmtP(p)}). ${NORMALITY_ADVICE[analysis] ?? ""}`.trim() });
    }
  }
  for (const rows of tablesEndingWith(results, "equalityVariance")) {
    for (const r of rows) {
      const p = num(r.p);
      if (p === null) continue;
      checked++;
      if (p < ALPHA) warn.push({ level: "warn", text: `Variâncias diferentes entre os grupos${typeof r.variable === "string" ? ` em ${r.variable}` : ""} (Levene, ${fmtP(p)}). Prefira o teste t de Welch.` });
    }
  }
  for (const rows of tablesEndingWith(results, "leveneTable")) {
    for (const r of rows) {
      const p = num(r.p), f = num(r.F);
      if (p === null) continue;
      checked++;
      const advice = analysis === "Anova" ? "Considere o teste de Kruskal-Wallis ou transformar a variável." : "Interprete com cautela ou transforme a variável.";
      if (p < ALPHA) warn.push({ level: "warn", text: `Homogeneidade de variâncias rejeitada (Levene${f !== null ? `, F = ${fmtStat(f)}` : ""}, ${fmtP(p)}). ${advice}` });
    }
  }

  if (warn.length > 0) return warn;
  return checked > 0 ? [{ level: "ok", text: "Pressupostos verificados automaticamente (α = 0,05): nenhum alerta." }] : [];
}
