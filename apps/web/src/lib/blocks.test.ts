import { describe, expect, it } from "vitest";
import type { Block, Dataset } from "../api";
import { exampleBlocks, moveBlock, newBlock, newId } from "./blocks";

const ds = (over: Partial<Dataset> = {}): Dataset => ({
  id: "a".repeat(32), name: "vendas.csv", table_name: "vendas", n_rows: 160, created_at: "",
  columns: [
    { name: "regiao", dtype: "VARCHAR", measurement: "nominal", n_distinct: 4 },
    { name: "grupo", dtype: "VARCHAR", measurement: "nominal", n_distinct: 2 },
    { name: "receita", dtype: "DOUBLE", measurement: "scale", n_distinct: null },
  ],
  ...over,
});
const text = (id: string): Block => ({ type: "text", id, markdown: id });

describe("newId", () => {
  it("é válido para a API (^[A-Za-z0-9_-]{1,64}$) e não repete ids existentes", () => {
    const ids = new Set<string>();
    for (let i = 0; i < 500; i++) { const id = newId(ids); expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/); expect(ids.has(id)).toBe(false); ids.add(id); }
  });
});

describe("moveBlock", () => {
  const list = [text("a"), text("b"), text("c")];
  it("troca de posição sem mutar a lista original", () => {
    expect(moveBlock(list, 1, -1).map((b) => b.id)).toEqual(["b", "a", "c"]);
    expect(moveBlock(list, 1, 1).map((b) => b.id)).toEqual(["a", "c", "b"]);
    expect(list.map((b) => b.id)).toEqual(["a", "b", "c"]);
  });
  it("nos limites (ou índice inválido) devolve a mesma lista", () => {
    expect(moveBlock(list, 0, -1)).toBe(list);
    expect(moveBlock(list, 2, 1)).toBe(list);
    expect(moveBlock(list, 9, -1)).toBe(list);
  });
});

describe("newBlock", () => {
  it("bloco de gráfico já nasce no modo sem SQL: média da 1ª numérica por categoria, com SQL gerado e gráfico de barras", () => {
    const b = newBlock("chart", [], [ds()]);
    expect(b).toMatchObject({
      type: "chart",
      builder: { dataset_id: "a".repeat(32), kind: "summary", group_by: "regiao", measures: [{ fn: "mean", column: "receita" }] },
      sql: 'SELECT "regiao", round(avg("receita"), 2) AS "média de receita" FROM "vendas" WHERE "regiao" IS NOT NULL GROUP BY 1 ORDER BY 1',
      chart: { type: "bar", x: "regiao", ys: ["média de receita"] },
    });
  });
  it("bloco de análise já vem com as variáveis efetivas (agrupamento de 2 níveis primeiro)", () => {
    const b = newBlock("analysis", [], [ds()]);
    expect(b).toMatchObject({ type: "analysis", dataset_id: "a".repeat(32), options: { dependent: ["receita"], group: "grupo" } });
  });
  it("sem datasets não quebra: dataset_id vazio e SQL vazio", () => {
    expect(newBlock("analysis", [], [])).toMatchObject({ dataset_id: "", options: { dependent: [], group: "" } });
    expect(newBlock("chart", [], [])).toMatchObject({ sql: "" });
  });
  it("id novo nunca colide com os blocos existentes", () => {
    const existing = Array.from({ length: 50 }, (_, i) => text(`t${i}`));
    expect(existing.map((b) => b.id)).not.toContain(newBlock("text", existing, []).id);
  });
});

describe("exampleBlocks", () => {
  it("monta texto + gráfico + comparação + análise a partir das colunas", () => {
    const blocks = exampleBlocks(ds());
    expect(blocks.map((b) => b.type)).toEqual(["text", "chart", "text", "analysis"]);
    const chart = blocks[1] as Extract<Block, { type: "chart" }>;
    expect(chart.sql).toBe('SELECT "regiao", round(avg("receita"), 2) AS media_receita FROM "vendas" GROUP BY 1 ORDER BY 1');
    expect(chart.chart).toEqual({ type: "bar", x: "regiao", ys: ["media_receita"], slots: { media_receita: 0 } });
    expect(new Set(blocks.map((b) => b.id)).size).toBe(blocks.length);
  });
  it("escapa aspas em nomes de coluna e normaliza o alias do SQL", () => {
    const d = ds({ columns: [
      { name: 'cat"x', dtype: "VARCHAR", measurement: "nominal", n_distinct: 3 },
      { name: "valor (R$)", dtype: "DOUBLE", measurement: "scale", n_distinct: null },
    ] });
    const chart = exampleBlocks(d).find((b) => b.type === "chart") as Extract<Block, { type: "chart" }>;
    expect(chart.sql).toBe('SELECT "cat""x", round(avg("valor (R$)"), 2) AS media_valor__R__ FROM "vendas" GROUP BY 1 ORDER BY 1');
  });
  it("sem coluna escalar: só o texto; sem agrupamento de 2 níveis: sem análise", () => {
    expect(exampleBlocks(ds({ columns: [{ name: "a", dtype: "VARCHAR", measurement: "nominal", n_distinct: 3 }] })).map((b) => b.type)).toEqual(["text"]);
    const noTwo = ds({ columns: [
      { name: "regiao", dtype: "VARCHAR", measurement: "nominal", n_distinct: 4 },
      { name: "receita", dtype: "DOUBLE", measurement: "scale", n_distinct: null },
    ] });
    expect(exampleBlocks(noTwo).map((b) => b.type)).toEqual(["text", "chart"]);
  });
});
