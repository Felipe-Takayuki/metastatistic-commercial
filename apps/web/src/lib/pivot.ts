import { formatCell, type JaspField } from "./format";

interface TableLike {
  schema: { fields: JaspField[] };
  data: Record<string, unknown>[];
}

const GROUPED = /^(.+)\[([^\]]+)\]$/;

/**
 * Algumas tabelas do JASP (ex.: "Chi-Squared Tests", "Nominal") chegam "de lado": UMA linha com grupos de colunas
 * `type[chiSquared]`, `value[chiSquared]`, `df[chiSquared]`, `p[chiSquared]`, `type[N]`, `value[N]`… Mostradas assim, os
 * cabeçalhos se repetem (Value df p Value df p) e o N fica colado ao teste. O JASP desktop as exibe transpostas
 * (uma linha por teste); isto faz o mesmo: grupos viram linhas e os nomes-base (type, value, df, p) viram colunas.
 *
 * Só transpõe quando é seguro: todas as colunas são `base[grupo]`, há uma única linha de dados, ao menos 2 grupos e cada
 * grupo tem a coluna `type` (o rótulo da linha). Caso contrário devolve `null` e a tabela é desenhada como veio.
 * As células saem já formatadas (cada uma com o formato da SUA coluna de origem: o N é inteiro, o valor do teste tem 3 casas).
 */
export function pivotColumnGroups<T extends TableLike>(table: T): { fields: JaspField[]; data: Record<string, unknown>[] } | null {
  const { fields } = table.schema;
  const { data } = table;
  if (data.length !== 1 || fields.length === 0) return null;
  const parsed = fields.map((f) => ({ f, m: GROUPED.exec(f.name) }));
  if (parsed.some((p) => !p.m)) return null;

  const groups: string[] = [];
  const bases: { name: string; title?: string }[] = [];
  const cell = new Map<string, JaspField>(); // `${grupo}\u0000${base}` -> coluna de origem
  for (const { f, m } of parsed) {
    const [, base, group] = m!;
    if (!groups.includes(group)) groups.push(group);
    if (!bases.some((b) => b.name === base)) bases.push({ name: base, title: f.title });
    cell.set(`${group}\u0000${base}`, f);
  }
  if (groups.length < 2 || groups.some((g) => !cell.has(`${g}\u0000type`))) return null;

  const row = data[0];
  const outFields: JaspField[] = bases.map((b) => ({ name: b.name, title: b.title, type: b.name === "type" ? "string" : "number" }));
  const outData = groups.map((g) =>
    Object.fromEntries(bases.map((b) => {
      const src = cell.get(`${g}\u0000${b.name}`);
      return [b.name, src ? formatCell(row[src.name], src) : ""];
    })),
  );
  return { fields: outFields, data: outData };
}
