import type { AnalysisBlock, Block, ChartBlock, Dataset, TextBlock } from "../api";
import { defaultState, problems, resolveState, toOptions, TTEST_DEF } from "./analyses";

/** Id curto e único dentro do relatório. `crypto.randomUUID` só existe em contexto seguro, então não dependemos dele. */
export function newId(taken: Iterable<string> = []): string {
  const used = new Set(taken);
  let id: string;
  do id = Math.random().toString(36).slice(2, 10).padEnd(8, "0"); while (used.has(id));
  return id;
}

export type BlockType = Block["type"];

export function newBlock(type: BlockType, blocks: Block[], datasets: Dataset[]): Block {
  const id = newId(blocks.map((b) => b.id));
  if (type === "text") return { type, id, markdown: "" } satisfies TextBlock;
  if (type === "chart") return { type, id, title: "", sql: datasets[0] ? `SELECT * FROM "${datasets[0].table_name}" LIMIT 20` : "", chart: null } satisfies ChartBlock;
  const ds = datasets[0];
  return { type, id, analysis: TTEST_DEF.id, dataset_id: ds?.id ?? "", options: toOptions(TTEST_DEF, resolveState(TTEST_DEF, ds, defaultState(TTEST_DEF))) } satisfies AnalysisBlock;
}

/** Move o bloco `index` em `delta` posições (±1), sem mutar. Fora dos limites devolve a mesma lista. */
export function moveBlock(blocks: Block[], index: number, delta: -1 | 1): Block[] {
  const to = index + delta;
  if (index < 0 || index >= blocks.length || to < 0 || to >= blocks.length) return blocks;
  const next = blocks.slice();
  [next[index], next[to]] = [next[to], next[index]];
  return next;
}

const quote = (id: string) => `"${id.replace(/"/g, '""')}"`;

/** Relatório de exemplo gerado a partir das colunas de um dataset (só inclui o que os dados permitem). */
export function exampleBlocks(ds: Dataset): Block[] {
  const blocks: Block[] = [];
  const add = (b: (id: string) => Block) => blocks.push(b(newId(blocks.map((x) => x.id))));
  const resolved = resolveState(TTEST_DEF, ds, defaultState(TTEST_DEF));
  const dep = resolved.vars.dependent[0];
  const grp = resolved.vars.group[0];
  const grpLevels = ds.columns.find((c) => c.name === grp)?.n_distinct ?? null;
  const cat = ds.columns.find((c) => c.measurement !== "scale" && c.n_distinct !== null && c.n_distinct >= 2 && c.n_distinct <= 12);
  const num = ds.columns.find((c) => c.measurement === "scale");

  add((id) => ({ type: "text", id, markdown: `# Análise de ${ds.name.replace(/\.csv$/i, "")}\n\nRelatório gerado a partir de **${ds.n_rows.toLocaleString("pt-BR")} linhas** e ${ds.columns.length} colunas. Edite este texto, reordene os blocos e adicione gráficos e análises.` }));
  if (cat && num) {
    const alias = `media_${num.name.replace(/[^A-Za-z0-9_]/g, "_")}`;
    add((id) => ({
      type: "chart", id, title: `Média de ${num.name} por ${cat.name}`,
      sql: `SELECT ${quote(cat.name)}, round(avg(${quote(num.name)}), 2) AS ${alias} FROM ${quote(ds.table_name)} GROUP BY 1 ORDER BY 1`,
      chart: { type: "bar", x: cat.name, ys: [alias], slots: { [alias]: 0 } },
    }));
  }
  if (dep && grp && grpLevels === 2 && problems(TTEST_DEF, ds, resolved).length === 0) {
    add((id) => ({ type: "text", id, markdown: `## Comparação entre grupos\n\nO teste t compara a média de **${dep}** entre os dois grupos de **${grp}**.` }));
    add((id) => ({ type: "analysis", id, analysis: TTEST_DEF.id, dataset_id: ds.id, options: toOptions(TTEST_DEF, resolved) }));
  }
  return blocks;
}
