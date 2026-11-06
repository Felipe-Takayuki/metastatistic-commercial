/**
 * Interpretação em texto do fator de Bayes, na classificação de Jeffreys adaptada por Lee & Wagenmakers (2013):
 * 1–3 anedótica, 3–10 moderada, 10–30 forte, 30–100 muito forte, >100 extrema (e o inverso a favor de H₀).
 * Lê as tabelas do resultado já exibido: não faz nenhuma execução extra.
 */
import type { Note } from "./assumptions";

/** Qualquer das três escalas do JASP → BF₁₀. */
export function toBF10(value: number, type: unknown): number {
  if (type === "BF01") return 1 / value;
  if (type === "LogBF10") return Math.exp(value);
  return value;
}

export interface Evidence { favors: "H1" | "H0" | "none"; strength: string; ratio: number }

/** Força da evidência de um BF₁₀. `ratio` é "quantas vezes" os dados favorecem o lado vencedor. */
export function evidence(bf10: number): Evidence {
  const favors = bf10 > 1 ? "H1" : bf10 < 1 ? "H0" : "none";
  const ratio = bf10 >= 1 ? bf10 : 1 / bf10;
  if (!(ratio > 1)) return { favors: "none", strength: "nenhuma evidência", ratio: 1 };
  const strength = ratio < 3 ? "anedótica" : ratio < 10 ? "moderada" : ratio < 30 ? "forte" : ratio < 100 ? "muito forte" : "extrema";
  return { favors, strength, ratio };
}

const comma = (s: string) => s.replace(".", ",");
/** Números muito grandes/pequenos em notação científica (6,86e+35), os demais com 2 casas. */
export function fmtBF(x: number): string {
  if (!Number.isFinite(x)) return String(x);
  return comma(x >= 1000 || x < 0.01 ? x.toExponential(2).replace("e+", "e") : x.toFixed(2));
}

type Row = Record<string, unknown>;
function tablesEndingWith(node: unknown, suffix: string, path = ""): Row[][] {
  if (!node || typeof node !== "object") return [];
  const o = node as Record<string, unknown>;
  const out: Row[][] = [];
  if (o.schema && typeof o.schema === "object" && Array.isArray(o.data) && path.endsWith(suffix)) out.push(o.data as Row[]);
  for (const [k, v] of Object.entries(o)) if (k !== "schema" && k !== "data" && k !== ".meta" && k !== "footnotes") out.push(...tablesEndingWith(v, suffix, `${path}/${k}`));
  return out;
}
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function label(r: Row): string {
  if (typeof r.variable1 === "string" && typeof r.variable2 === "string") return `${r.variable1} − ${r.variable2}`;
  return typeof r.variable === "string" ? r.variable : "";
}

function sentence(bf10: number, subject: string, h1: string, h0: string): string {
  const e = evidence(bf10);
  const head = `${subject}BF₁₀ = ${fmtBF(bf10)}`;
  if (e.favors === "none") return `${head}: os dados não favorecem nem H₁ nem H₀.`;
  const side = e.favors === "H1" ? h1 : h0;
  return `${head}: evidência ${e.strength} a favor de ${side} (os dados são ${fmtBF(e.ratio)} vezes mais prováveis sob ${e.favors === "H1" ? "H₁" : "H₀"} do que sob ${e.favors === "H1" ? "H₀" : "H₁"}).`;
}

const T_TESTS = new Set(["TTestBayesianIndependentSamples", "TTestBayesianPairedSamples", "TTestBayesianOneSample"]);

/** Notas de interpretação do fator de Bayes; lista vazia se a análise não é bayesiana ou a tabela não traz números. */
export function bayesNotes(analysis: string, options: Record<string, unknown>, results: unknown): Note[] {
  const type = options.bayesFactorType;
  const notes: Note[] = [];
  if (T_TESTS.has(analysis)) {
    const directional = options.alternative === "greater" || options.alternative === "less";
    const h1 = directional ? "H₁ (unilateral)" : "H₁ (há diferença)";
    const h0 = directional ? "H₀ (sem efeito na direção testada)" : "H₀ (não há diferença)";
    for (const rows of tablesEndingWith(results, "ttestTable")) {
      for (const r of rows) {
        const v = num(r.BF);
        if (v === null) continue;
        const name = label(r);
        notes.push({ level: "info", text: sentence(toBF10(v, type), name ? `${name}: ` : "", h1, h0) });
      }
    }
  } else if (analysis === "CorrelationBayesian") {
    const dir = options.alternative === "greater" ? " (positiva)" : options.alternative === "less" ? " (negativa)" : "";
    for (const rows of tablesEndingWith(results, "corBayesTable")) {
      for (const r of rows) {
        const v = num(r.pearsonbf);
        if (v === null) continue;
        const name = typeof r.variable1 === "string" && typeof r.variable2 === "string" ? `${r.variable1} × ${r.variable2}: ` : "";
        notes.push({ level: "info", text: sentence(toBF10(v, type), name, `H₁ (há correlação${dir})`, "H₀ (não há correlação, ρ = 0)") });
      }
    }
  } else if (analysis === "ContingencyTablesBayesian") {
    for (const rows of tablesEndingWith(results, "contTabBasBF")) {
      for (const r of rows) {
        const v = num(r["value[BF]"]);
        if (v === null) continue;
        notes.push({ level: "info", text: sentence(toBF10(v, type), "", "H₁ (as variáveis estão associadas)", "H₀ (as variáveis são independentes)") });
      }
    }
  } else if ((analysis === "AnovaBayesian" || analysis === "AncovaBayesian") && (type === undefined || type === "BF10")) {
    // BF de inclusão: quanto a presença do efeito nos modelos é favorecida pelos dados
    for (const rows of tablesEndingWith(results, "tableEffects")) {
      for (const r of rows) {
        const v = num(r.BFInclusion);
        if (v === null || typeof r.Effects !== "string") continue;
        const e = evidence(v);
        const effect = r.Effects.replace(/ ✻ /g, " × ");
        notes.push({
          level: "info",
          text: e.favors === "none"
            ? `${effect}: BF de inclusão = ${fmtBF(v)}: os dados não favorecem nem incluir nem excluir o efeito.`
            : `${effect}: BF de inclusão = ${fmtBF(v)}: evidência ${e.strength} a favor de ${e.favors === "H1" ? "incluir" : "excluir"} o efeito no modelo.`,
        });
      }
    }
  }
  if (notes.length > 0) notes.push({ level: "info", text: "Classificação de Jeffreys, adaptada por Lee e Wagenmakers (2013): 1–3 anedótica, 3–10 moderada, 10–30 forte, 30–100 muito forte, acima de 100 extrema." });
  return notes;
}
