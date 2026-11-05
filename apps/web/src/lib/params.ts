import type { DashFilter } from "../api";

export type Resolved = { sql: string } | { error: string };
export const isError = (r: Resolved): r is { error: string } => "error" in r;

const PLACEHOLDER = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

/** Nomes de filtro usados no SQL (`{{nome}}`), sem repetição, na ordem em que aparecem. */
export function paramsIn(sql: string): string[] {
  return [...new Set([...sql.matchAll(PLACEHOLDER)].map((m) => m[1]))];
}

/**
 * Valor do filtro -> literal SQL seguro. Vazio vira NULL (o autor escreve `({{g}} IS NULL OR col = {{g}})`).
 * Texto: aspas simples duplicadas (o DuckDB não usa barra invertida em literais comuns); número: só dígitos, sinal e ponto/vírgula
 * decimal; data: AAAA-MM-DD válida. Nada do que o usuário digita vira SQL.
 */
export function literal(f: DashFilter, raw: string): Resolved {
  const v = raw.replace(/\0/g, "").trim();
  if (v === "") return { sql: "NULL" };
  if (f.type === "text") return { sql: `'${raw.replace(/\0/g, "").replace(/'/g, "''")}'` };
  if (f.type === "number") {
    if (!/^-?\d+([.,]\d+)?$/.test(v)) return { error: `Valor inválido para o filtro "${f.label || f.name}": digite um número.` };
    return { sql: v.replace(",", ".") };
  }
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  const date = d && new Date(Date.UTC(+d[1], +d[2] - 1, +d[3]));
  if (!d || !date || date.getUTCFullYear() !== +d[1] || date.getUTCMonth() !== +d[2] - 1 || date.getUTCDate() !== +d[3])
    return { error: `Valor inválido para o filtro "${f.label || f.name}": use a data no formato AAAA-MM-DD.` };
  return { sql: `DATE '${v}'` };
}

/** Troca cada `{{nome}}` pelo literal do valor atual. Parâmetro sem filtro declarado ou valor inválido -> erro (o tile não consulta). */
export function substitute(sql: string, filters: readonly DashFilter[], values: Readonly<Record<string, string>>): Resolved {
  let error: string | undefined;
  const out = sql.replace(PLACEHOLDER, (_, name: string) => {
    const f = filters.find((x) => x.name === name);
    if (!f) { error ??= `Filtro desconhecido: {{${name}}}. Crie-o em "Filtros do dashboard".`; return ""; }
    const r = literal(f, values[name] ?? f.default);
    if (isError(r)) { error ??= r.error; return ""; }
    return r.sql;
  });
  return error ? { error } : { sql: out };
}

/** Valores iniciais: o padrão de cada filtro; mantém o que o usuário já digitou para filtros que continuam existindo. */
export function reconcileValues(filters: readonly DashFilter[], prev: Readonly<Record<string, string>>): Record<string, string> {
  return Object.fromEntries(filters.map((f) => [f.name, prev[f.name] ?? f.default]));
}

/** Nome de filtro digitado -> nome válido (letras, dígitos e `_`; não começa com dígito). */
export function sanitizeName(raw: string): string {
  const n = raw.replace(/[^A-Za-z0-9_]/g, "_").slice(0, 40);
  return /^[0-9]/.test(n) ? `_${n}`.slice(0, 40) : n;
}

/** Problemas que impedem salvar a lista de filtros (o servidor responderia 422). */
export function filterProblems(filters: readonly DashFilter[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const f of filters) {
    if (!f.name) out.push("Há um filtro sem nome.");
    else if (seen.has(f.name)) out.push(`Nome de filtro repetido: ${f.name}.`);
    seen.add(f.name);
  }
  return out;
}
