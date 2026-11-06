/**
 * Montador "sem SQL" de gráficos e KPIs: a pessoa escolhe dataset, coluna e cálculo; o SQL é gerado aqui.
 * O que roda continua sendo o SQL (mesmo sandbox de sempre); o montador só o escreve por ela.
 */
import type { ChartConfig, Column, Dataset, Measure, MeasureFn, QueryBuilder } from "../api";

export const MEASURE_LABEL: Record<Exclude<MeasureFn, "value">, string> = {
  count: "número de linhas", mean: "média", sum: "soma", min: "mínimo", max: "máximo", median: "mediana",
};
export const MAX_MEASURES = 3;
export const MAX_POINTS = 5000;

const NUMERIC = /^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|DECIMAL)/i;
export const isNumeric = (c: Column) => NUMERIC.test(c.dtype);
const q = (id: string) => `"${id.replace(/"/g, '""')}"`;

const labelOf = (m: Measure): string => (m.fn === "count" ? "linhas" : m.fn === "value" ? m.column : `${MEASURE_LABEL[m.fn]} de ${m.column}`);

/** Nomes das colunas do resultado (sem repetir: duas medidas iguais ganham 2, 3…). */
export function measureAliases(measures: Measure[]): string[] {
  const seen = new Map<string, number>();
  return measures.map((m) => {
    const base = labelOf(m);
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return n === 1 ? base : `${base} ${n}`;
  });
}

const aggregate = (m: Measure): string => {
  const col = q(m.column);
  switch (m.fn) {
    case "count": return "count(*)";
    case "mean": return `round(avg(${col}), 2)`;
    case "median": return `round(median(${col}), 2)`;
    case "sum": return `sum(${col})`;
    case "min": return `min(${col})`;
    case "max": return `max(${col})`;
    case "value": return col;
  }
};

/** O que falta escolher (null = pronto). `ds` é o dataset do montador. */
export function builderProblem(b: QueryBuilder, ds: Dataset | undefined, kind: "chart" | "kpi"): string | null {
  if (!ds) return "escolha um dataset";
  const col = (name: string) => ds.columns.find((c) => c.name === name);
  if (kind === "chart" && b.kind === "summary" && !col(b.group_by)) return "escolha a coluna que define as categorias";
  if (kind === "chart" && b.kind === "points" && !col(b.group_by)) return "escolha a coluna do eixo X";
  for (const m of b.measures) {
    if (m.fn === "count") continue;
    const c = col(m.column);
    if (!c) return b.kind === "points" ? "escolha a coluna do eixo Y" : "escolha a coluna de cada cálculo";
    if ((m.fn !== "min" && m.fn !== "max" && m.fn !== "value") && !isNumeric(c)) return `“${m.column}” não é numérica: use contagem, mínimo ou máximo, ou outra coluna`;
    if (m.fn === "value" && !isNumeric(c)) return `“${m.column}” não é numérica: o eixo Y precisa de números`;
  }
  if (b.kind === "points" && !isNumeric(col(b.group_by) ?? ({ dtype: "" } as Column))) return `“${b.group_by}” não é numérica: a dispersão precisa de números nos dois eixos`;
  return null;
}

/** SQL do montador. Resumo: uma linha por categoria (ordenada); pontos: as linhas com X e Y preenchidos; KPI: uma linha só. */
export function buildSql(b: QueryBuilder, ds: Dataset): string {
  const from = q(ds.table_name);
  const aliases = measureAliases(b.measures);
  const cols = b.measures.map((m, i) => `${aggregate(m)} AS ${q(aliases[i])}`).join(", ");
  if (b.kind === "points") {
    const notNull = [b.group_by, ...b.measures.map((m) => m.column)].map((c) => `${q(c)} IS NOT NULL`).join(" AND ");
    return `SELECT ${q(b.group_by)}, ${cols} FROM ${from} WHERE ${notNull} LIMIT ${MAX_POINTS}`;
  }
  if (!b.group_by) return `SELECT ${cols} FROM ${from}`;
  return `SELECT ${q(b.group_by)}, ${cols} FROM ${from} WHERE ${q(b.group_by)} IS NOT NULL GROUP BY 1 ORDER BY 1`;
}

/** Montador inicial para um dataset: gráfico = média da 1ª coluna numérica por categoria (ou contagem); KPI = número de linhas. */
export function defaultBuilder(kind: "chart" | "kpi", ds: Dataset): QueryBuilder {
  if (kind === "kpi") return { dataset_id: ds.id, kind: "summary", group_by: "", measures: [{ fn: "count", column: "" }] };
  const num = ds.columns.find(isNumeric);
  const cat = ds.columns.find((c) => !isNumeric(c) && (c.n_distinct ?? 0) >= 1 && (c.n_distinct ?? 0) <= 30) ?? ds.columns.find((c) => !isNumeric(c) && c !== num);
  const group_by = (cat ?? ds.columns[0])?.name ?? "";
  const measure: Measure = num && num.name !== group_by ? { fn: "mean", column: num.name } : { fn: "count", column: "" };
  return { dataset_id: ds.id, kind: "summary", group_by, measures: [measure] };
}

/** Troca de dataset/tipo/cálculo mantendo só o que ainda faz sentido (colunas inexistentes são trocadas por uma válida). */
export function repair(b: QueryBuilder, ds: Dataset, kind: "chart" | "kpi"): QueryBuilder {
  const names = new Set(ds.columns.map((c) => c.name));
  const base = defaultBuilder(kind, ds);
  const group_by = kind === "kpi" ? "" : names.has(b.group_by) ? b.group_by : base.group_by;
  const measures = b.measures.map((m) => (m.fn === "count" || names.has(m.column) ? m : base.measures[0].fn === "count" ? { fn: "count" as const, column: "" } : base.measures[0]));
  return { ...b, dataset_id: ds.id, group_by, measures };
}

/** Frase curta do que o gráfico mostra, para o cabeçalho do montador. */
export function describeBuilder(b: QueryBuilder): string {
  const what = measureAliases(b.measures).join(", ");
  return b.kind === "points" ? `${what} × ${b.group_by}` : b.group_by ? `${what} por ${b.group_by}` : what;
}

const TEMPORAL = /^(DATE|TIMESTAMP)/i;

/** Gráfico que combina com as escolhas: pontos = dispersão; resumo = barras (ou linha, se já era linha ou se o eixo é uma data). */
export function chartFor(b: QueryBuilder, ds: Dataset, prev: ChartConfig | null): ChartConfig {
  const ys = measureAliases(b.measures);
  const slots = Object.fromEntries(ys.map((y, i) => [y, i]));
  if (b.kind === "points") return { type: "scatter", x: b.group_by, ys, slots };
  const isDate = TEMPORAL.test(ds.columns.find((c) => c.name === b.group_by)?.dtype ?? "");
  const type = prev?.type === "line" || prev?.type === "bar" ? prev.type : isDate ? "line" : "bar";
  return { type, x: b.group_by, ys, slots };
}
