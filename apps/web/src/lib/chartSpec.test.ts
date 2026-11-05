import { describe, expect, it } from "vitest";
import type { QueryResult } from "../api";
import { buildChart, freeSlot, MAX_BAR_CATEGORIES, reconcile, suggestSpec, type ChartSpec, type ChartTokens } from "./chartSpec";

const tokens: ChartTokens = { surface: "#fcfcfb", text: "#0b0b0b", textSecondary: "#52514e", grid: "#e4e3df", axis: "#c9c8c3", series: ["#2a78d6", "#eb6834", "#1baf7a"] };
const result = (cols: [string, string][], rows: unknown[][]): QueryResult => ({
  columns: cols.map(([name, dtype]) => ({ name, dtype })), rows, row_count: rows.length, truncated: false, elapsed_ms: 1,
});
const sales = result([["regiao", "VARCHAR"], ["receita", "DOUBLE"], ["custo", "DOUBLE"]], [["Sul", 30, 10], ["Norte", 15, 12]]);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const opt = (o: Record<string, unknown>) => o as any;

describe("suggestSpec", () => {
  it("categoria + número -> barras", () => {
    expect(suggestSpec(sales)).toMatchObject({ type: "bar", x: "regiao", ys: ["receita"], slots: { receita: 0 } });
  });
  it("data -> linha; número+número -> dispersão", () => {
    expect(suggestSpec(result([["d", "DATE"], ["v", "BIGINT"]], [["2024-01-01", 1]]))?.type).toBe("line");
    expect(suggestSpec(result([["a", "DOUBLE"], ["b", "DOUBLE"]], [[1, 2]]))?.type).toBe("scatter");
  });
  it("muitas categorias -> linha em vez de barras ilegíveis", () => {
    const rows = Array.from({ length: MAX_BAR_CATEGORIES + 1 }, (_, i) => [`c${i}`, i]);
    expect(suggestSpec(result([["c", "VARCHAR"], ["v", "BIGINT"]], rows))?.type).toBe("line");
  });
  it("sem coluna numérica ou sem linhas -> sem gráfico", () => {
    expect(suggestSpec(result([["a", "VARCHAR"]], [["x"]]))).toBeNull();
    expect(suggestSpec(result([["a", "VARCHAR"], ["b", "DOUBLE"]], []))).toBeNull();
  });
});

describe("freeSlot — cor segue a série, não o ranking", () => {
  it("remover a 1ª série não repinta as sobreviventes", () => {
    const slots = { a: 0, b: 1, c: 2 };
    expect(freeSlot(slots, ["b", "c"])).toBe(0); // a saiu: slot 0 livre
    expect(slots.b).toBe(1); // b continua laranja
  });
  it("sem vaga quando as 3 estão em uso", () => {
    expect(freeSlot({ a: 0, b: 1, c: 2 }, ["a", "b", "c"])).toBeUndefined();
  });
});

describe("buildChart", () => {
  const bar: ChartSpec = { type: "bar", x: "regiao", ys: ["receita"], slots: { receita: 0 } };

  it("barras: <=24px, data-end arredondado 4px, base no zero, sem legenda com 1 série", () => {
    const o = opt(buildChart(sales, bar, tokens).option);
    expect(o.series[0]).toMatchObject({ type: "bar", barMaxWidth: 24, itemStyle: { color: "#2a78d6", borderRadius: [4, 4, 0, 0] } });
    expect(o.legend).toBeUndefined();
    expect(o.yAxis.min({ min: 5 })).toBe(0); // barras sempre ancoradas no zero
    expect(o.yAxis.min({ min: -3 })).toBe(-3); // ...exceto se houver negativos
    expect(o.yAxis.splitLine.lineStyle).toMatchObject({ width: 1, type: "solid" });
  });
  it("2+ séries: legenda presente e cores pela posição fixa (slot)", () => {
    const spec: ChartSpec = { ...bar, ys: ["custo", "receita"], slots: { receita: 0, custo: 1 } };
    const o = opt(buildChart(sales, spec, tokens).option);
    expect(o.legend.data).toEqual(["custo", "receita"]);
    expect(o.series.map((s: { itemStyle: { color: string } }) => s.itemStyle.color)).toEqual(["#eb6834", "#2a78d6"]);
  });
  it("rótulo de valor só quando há poucas marcas", () => {
    expect(opt(buildChart(sales, bar, tokens).option).series[0].label.show).toBe(true);
    const many = result([["c", "VARCHAR"], ["v", "DOUBLE"]], Array.from({ length: 9 }, (_, i) => [`c${i}`, i]));
    expect(opt(buildChart(many, { ...bar, x: "c", ys: ["v"], slots: { v: 0 } }, tokens).option).series[0].label).toBeUndefined();
  });
  it("mais de 10 categorias -> barras horizontais com data-end à direita", () => {
    const rows = Array.from({ length: 12 }, (_, i) => [`cat ${i}`, i + 1]);
    const o = opt(buildChart(result([["c", "VARCHAR"], ["v", "DOUBLE"]], rows), { ...bar, x: "c", ys: ["v"], slots: { v: 0 } }, tokens).option);
    expect(o.yAxis.type).toBe("category");
    expect(o.series[0].itemStyle.borderRadius).toEqual([0, 4, 4, 0]);
  });
  it("recusa >3 séries, barras demais e dispersão com X textual (em vez de desenhar errado)", () => {
    const many = result([["x", "VARCHAR"], ["a", "DOUBLE"], ["b", "DOUBLE"], ["c", "DOUBLE"], ["d", "DOUBLE"]], [["k", 1, 2, 3, 4]]);
    expect(buildChart(many, { type: "line", x: "x", ys: ["a", "b", "c", "d"], slots: {} }, tokens).problem).toMatch(/máximo 3/);
    const rows = Array.from({ length: MAX_BAR_CATEGORIES + 1 }, (_, i) => [`c${i}`, i]);
    expect(buildChart(result([["c", "VARCHAR"], ["v", "DOUBLE"]], rows), { ...bar, x: "c", ys: ["v"], slots: { v: 0 } }, tokens).problem).toMatch(/ilegíveis/);
    expect(buildChart(sales, { ...bar, type: "scatter" }, tokens).problem).toMatch(/numérica/);
  });
  it("linha: 2px, hairline, tooltip por eixo; rótulo final só se as séries não colidem", () => {
    const r = result([["d", "DATE"], ["a", "DOUBLE"], ["b", "DOUBLE"]], [["2024-01-01", 0, 100], ["2024-01-02", 10, 90]]);
    const spec: ChartSpec = { type: "line", x: "d", ys: ["a", "b"], slots: { a: 0, b: 1 } };
    const o = opt(buildChart(r, spec, tokens).option);
    expect(o.series[0].lineStyle.width).toBe(2);
    expect(o.tooltip.trigger).toBe("axis");
    expect(o.series[0].endLabel?.show).toBe(true); // 10 vs 90: bem separados
    const close = result([["d", "DATE"], ["a", "DOUBLE"], ["b", "DOUBLE"]], [["2024-01-01", 0, 100], ["2024-01-02", 50, 52]]);
    expect(opt(buildChart(close, spec, tokens).option).series[0].endLabel).toBeUndefined(); // 50 vs 52: colidiriam -> legenda
  });
  it("dispersão: ponto de 8px com anel de superfície + alvo de hover invisível de 24px", () => {
    const r = result([["x", "DOUBLE"], ["y", "DOUBLE"]], [[1, 2], [3, 4], [null, 5]]);
    const o = opt(buildChart(r, { type: "scatter", x: "x", ys: ["y"], slots: { y: 0 } }, tokens).option);
    expect(o.series).toHaveLength(2);
    expect(o.series[0]).toMatchObject({ symbolSize: 8, silent: true, itemStyle: { borderColor: "#fcfcfb", borderWidth: 2 } });
    expect(o.series[1]).toMatchObject({ symbolSize: 24, itemStyle: { opacity: 0 } });
    expect(o.series[0].data).toEqual([[1, 2], [3, 4]]); // linha com X nulo descartada
  });
  it("eixo compacto só quando os valores chegam a 10.000", () => {
    const big = result([["c", "VARCHAR"], ["v", "DOUBLE"]], [["a", 25_000], ["b", 5]]);
    expect(opt(buildChart(big, { ...bar, x: "c", ys: ["v"], slots: { v: 0 } }, tokens).option).yAxis.axisLabel.formatter(25_000)).toBe("25K");
    expect(opt(buildChart(sales, bar, tokens).option).yAxis.axisLabel.formatter(2500)).toBe("2,500");
  });
});

describe("reconcile — gráfico salvo x consulta atual", () => {
  const saved: ChartSpec = { type: "line", x: "regiao", ys: ["receita"], slots: { receita: 1 } };
  it("se as colunas ainda existem, mantém exatamente o gráfico salvo (tipo e cor incluídos)", () => {
    expect(reconcile(saved, sales)).toBe(saved);
  });
  it("se o SQL mudou e as colunas sumiram, volta à sugestão automática", () => {
    const other = result([["mes", "VARCHAR"], ["total", "DOUBLE"]], [["jan", 5]]);
    expect(reconcile(saved, other)).toMatchObject({ type: "bar", x: "mes", ys: ["total"] });
  });
  it("sem gráfico salvo, sugere; sem coluna numérica, não há gráfico", () => {
    expect(reconcile(null, sales)).toMatchObject({ x: "regiao", ys: ["receita"] });
    expect(reconcile(saved, result([["a", "VARCHAR"]], [["x"]]))).toBeNull();
  });
  it("gráfico salvo sem séries é tratado como inválido", () => {
    expect(reconcile({ ...saved, ys: [] }, sales)).toMatchObject({ ys: ["receita"] });
  });
});
