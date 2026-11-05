/** Formatação de tabelas estatísticas (estilo APA) a partir do `format` do schema do jaspResults. */

export interface JaspField {
  name: string;
  title?: string;
  type?: "string" | "number" | "integer" | "pvalue" | string;
  format?: string;
  combine?: boolean;
}

/** "sf:4;dp:3;p:.001" -> { sf: 4, dp: 3, p: 0.001 } (chaves sem valor numérico viram `true`). */
export function parseFormat(format?: string): Record<string, number | true> {
  const out: Record<string, number | true> = {};
  for (const part of (format ?? "").split(";")) {
    const [key, raw] = part.split(":");
    if (!key) continue;
    const n = raw === undefined ? NaN : Number(raw);
    out[key.trim()] = raw === undefined || Number.isNaN(n) ? true : n;
  }
  return out;
}

const stripLeadingZero = (s: string) => s.replace(/^(-?)0\./, "$1.");

export function formatNumber(value: number, field: JaspField): string {
  if (!Number.isFinite(value)) return Number.isNaN(value) ? "NaN" : value > 0 ? "∞" : "-∞";
  const f = parseFormat(field.format);
  const isP = field.type === "pvalue" || typeof f.p === "number";
  if (field.type === "integer") return String(Math.round(value));

  if (isP) {
    const threshold = typeof f.p === "number" ? f.p : 0.001;
    const dp = typeof f.dp === "number" ? f.dp : 3;
    return value < threshold ? `< ${stripLeadingZero(String(threshold))}` : stripLeadingZero(value.toFixed(dp));
  }

  const dp = typeof f.dp === "number" ? f.dp : undefined;
  const sf = typeof f.sf === "number" ? f.sf : undefined;
  if (dp === undefined && sf === undefined) return String(value);
  if (dp === undefined) return Number(value.toPrecision(sf)).toString();
  // Números grandes: significant figures mandam (evita "12345.678" com 4 sf).
  if (sf !== undefined && Math.abs(value) >= 10 ** sf) return String(Math.round(value));
  const fixed = value.toFixed(dp);
  // Valor não nulo que zera ao arredondar -> notação científica em vez de "0.000".
  if (sf !== undefined && value !== 0 && Number(fixed) === 0) return value.toExponential(Math.max(sf - 1, 1));
  return fixed;
}

export function formatCell(value: unknown, field: JaspField): string {
  if (value === null || value === undefined || value === "") return "";
  // Célula com formato próprio (ex.: mediana/mínimo/máximo nas descritivas): { value, type, format }
  if (typeof value === "object" && !Array.isArray(value) && "value" in value) {
    const c = value as { value: unknown; type?: string; format?: string };
    return formatCell(c.value, { ...field, type: c.type ?? field.type, format: c.format ?? field.format });
  }
  if (typeof value === "number") return formatNumber(value, field);
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** Valores de dados brutos (preview/SQL): como estão armazenados, nulos como "—". */
export function formatRaw(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(12)));
  if (typeof value === "boolean") return value ? "true" : "false";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** Eixos/tooltips de gráfico: mesmo formato dos dados (ponto decimal, vírgula de milhar); compacto (K/M/B) a partir de 10.000. */
export function formatAxis(value: number, compact: boolean): string {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  if (compact && abs >= 10_000) {
    const [div, suffix] = abs >= 1e9 ? [1e9, "B"] : abs >= 1e6 ? [1e6, "M"] : [1e3, "K"];
    return `${Number((value / div).toPrecision(3))}${suffix}`;
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: abs < 1 ? 4 : 2 }).format(value);
}
