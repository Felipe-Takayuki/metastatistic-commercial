/**
 * Constrói opções do ECharts seguindo o método de dataviz:
 * barras <=24px com data-end arredondado em 4px, linhas 2px, grade hairline, legenda com >=2 séries,
 * no máximo 3 séries (limite validado em todos os pares), cor presa à série (não ao ranking).
 */
import type { ChartConfig, QueryResult } from "../api";
import { formatAxis } from "./format";

export type ChartType = ChartConfig["type"];
export const MAX_SERIES = 3;
export const MAX_BAR_CATEGORIES = 60;
const COMPACT_FROM = 10_000;

/** Mesma forma do que é salvo nos relatórios. `slots`: sobreviventes de um filtro nunca mudam de cor. */
export type ChartSpec = ChartConfig;

export interface ChartTokens {
  surface: string;
  text: string;
  textSecondary: string;
  grid: string;
  axis: string;
  series: string[];
}

const NUMERIC = /^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|DECIMAL)/i;
const TEMPORAL = /^(DATE|TIMESTAMP)/i;
export const isNumericType = (dtype: string) => NUMERIC.test(dtype);
export const isTemporalType = (dtype: string) => TEMPORAL.test(dtype);

/** Menor posição livre da paleta; undefined se as 3 estiverem ocupadas. */
export function freeSlot(slots: Record<string, number>, ys: string[]): number | undefined {
  const used = new Set(ys.map((c) => slots[c]));
  return [0, 1, 2].find((s) => !used.has(s));
}

export function suggestSpec(result: QueryResult): ChartSpec | null {
  const cols = result.columns;
  const numeric = cols.filter((c) => isNumericType(c.dtype));
  if (numeric.length === 0 || result.rows.length === 0) return null;
  const xCol = cols.find((c) => !isNumericType(c.dtype)) ?? cols[0];
  const y = numeric.find((c) => c.name !== xCol.name);
  if (!y) return null;
  const type: ChartType = isTemporalType(xCol.dtype)
    ? "line"
    : isNumericType(xCol.dtype)
      ? "scatter"
      : result.rows.length <= MAX_BAR_CATEGORIES
        ? "bar"
        : "line";
  return { type, x: xCol.name, ys: [y.name], slots: { [y.name]: 0 } };
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export interface BuiltChart {
  option: Record<string, unknown>;
  /** Motivo pelo qual o gráfico não pode ser desenhado (mostrado no lugar dele). */
  problem?: string;
}

export function buildChart(result: QueryResult, spec: ChartSpec, t: ChartTokens): BuiltChart {
  const xi = result.columns.findIndex((c) => c.name === spec.x);
  const yis = spec.ys.map((n) => result.columns.findIndex((c) => c.name === n));
  if (xi < 0 || yis.some((i) => i < 0) || yis.length === 0) return { option: {}, problem: "Escolha as colunas do gráfico." };
  if (spec.ys.length > MAX_SERIES) return { option: {}, problem: `No máximo ${MAX_SERIES} séries.` };
  if (spec.type === "scatter" && !isNumericType(result.columns[xi].dtype))
    return { option: {}, problem: "Dispersão exige uma coluna X numérica." };
  const nCats = result.rows.length;
  if (spec.type === "bar" && nCats > MAX_BAR_CATEGORIES)
    return { option: {}, problem: `Barras com mais de ${MAX_BAR_CATEGORIES} categorias ficam ilegíveis (${nCats}). Escolha uma coluna com menos categorias ou use linha.` };

  const color = (col: string) => t.series[spec.slots[col] ?? 0];
  const multi = spec.ys.length >= 2;
  const allY = yis.flatMap((i) => result.rows.map((r) => num(r[i]))).filter((v): v is number => v !== null);
  const compact = allY.length > 0 && Math.max(...allY.map(Math.abs)) >= COMPACT_FROM;
  const fmt = (v: unknown) => (typeof v === "number" ? formatAxis(v, false) : String(v ?? "—"));

  const common = {
    animationDuration: 250,
    textStyle: { fontFamily: "inherit", color: t.textSecondary },
    grid: { left: 8, right: 24, top: multi ? 40 : 16, bottom: 8, containLabel: true },
    legend: multi
      ? {
          top: 0, left: 0, itemWidth: spec.type === "line" ? 20 : 12, itemHeight: spec.type === "line" ? 3 : 12, itemGap: 18,
          icon: spec.type === "scatter" ? "circle" : "roundRect",
          textStyle: { color: t.text, fontSize: 12 },
          data: spec.ys,
        }
      : undefined,
    tooltip: tooltipBase(t),
  };
  const gridLine = { show: true, lineStyle: { color: t.grid, width: 1, type: "solid" } };
  const valueAxis = (scale: boolean) => ({
    type: "value", scale, min: scale ? undefined : (v: { min: number }) => Math.min(0, v.min),
    axisLine: { show: false }, axisTick: { show: false }, splitLine: gridLine,
    axisLabel: { color: t.textSecondary, fontSize: 12, formatter: (v: number) => formatAxis(v, compact) },
  });

  if (spec.type === "scatter") {
    const series = spec.ys.flatMap((name, k) => {
      const pts = result.rows
        .map((r) => [num(r[xi]), num(r[yis[k]])] as const)
        .filter((p): p is readonly [number, number] => p[0] !== null && p[1] !== null)
        .map((p) => [p[0], p[1]]);
      return [
        // marca visível: 8px com anel de 2px da cor da superfície; não recebe ponteiro
        { name, type: "scatter", data: pts, symbolSize: 8, silent: true, z: 3, itemStyle: { color: color(name), borderColor: t.surface, borderWidth: 2 } },
        // alvo de hover de 24px, invisível (a marca de 8px sozinha é um alvo impossível)
        { name, type: "scatter", data: pts, symbolSize: 24, z: 2, itemStyle: { opacity: 0 }, emphasis: { itemStyle: { opacity: 0.12, color: color(name) } },
          tooltip: { trigger: "item", formatter: (p: { data: number[] }) => pointTooltip(name, spec.x, p.data[0], p.data[1], color(name), t, fmt) } },
      ];
    });
    return {
      option: {
        ...common, series,
        legend: common.legend && { ...common.legend, selectedMode: false },
        xAxis: { ...valueAxis(true), axisLabel: { ...valueAxis(true).axisLabel, formatter: (v: number) => formatAxis(v, false) }, splitLine: { show: false },
          axisLine: { show: true, lineStyle: { color: t.axis } } },
        yAxis: valueAxis(true),
        tooltip: { ...tooltipBase(t), trigger: "item" },
      },
    };
  }

  const cats = result.rows.map((r) => (r[xi] === null || r[xi] === undefined ? "—" : String(r[xi])));
  const horizontal = spec.type === "bar" && cats.length > 10;
  const catAxis = {
    type: "category", data: cats, inverse: horizontal, boundaryGap: spec.type === "bar",
    axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false },
    axisLabel: { color: t.textSecondary, fontSize: 12, hideOverlap: true, ...(horizontal ? { width: 140, overflow: "truncate" } : {}) },
  };
  const valAxis = valueAxis(spec.type === "line");

  const labelBars = spec.type === "bar" && cats.length * spec.ys.length <= 8;
  const finals = spec.ys.map((_, k) => num(result.rows[result.rows.length - 1]?.[yis[k]]));
  const range = allY.length ? Math.max(...allY) - Math.min(...allY) : 0;
  const finalsSeparate = finals.every((a, i) => finals.every((b, j) => i === j || a === null || b === null || Math.abs(a - b) >= range * 0.1));

  const series = spec.ys.map((name, k) => {
    const data = result.rows.map((r) => num(r[yis[k]]));
    if (spec.type === "bar") {
      return {
        name, type: "bar", data, barMaxWidth: 24, barGap: "12%",
        itemStyle: { color: color(name), borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
        emphasis: { itemStyle: { color: color(name), shadowBlur: 0, borderColor: t.text, borderWidth: 1 } },
        label: labelBars ? { show: true, position: horizontal ? "right" : "top", color: t.textSecondary, fontSize: 12, formatter: (p: { value: number }) => fmt(p.value) } : undefined,
      };
    }
    return {
      name, type: "line", data, showSymbol: false, symbolSize: 8, connectNulls: false,
      lineStyle: { width: 2, color: color(name), cap: "round", join: "round" },
      itemStyle: { color: color(name), borderColor: t.surface, borderWidth: 2 },
      emphasis: { focus: "none" },
      endLabel: multi && finalsSeparate ? { show: true, formatter: name, color: t.text, fontSize: 12 } : undefined,
    };
  });

  return {
    option: {
      ...common, series,
      grid: { ...common.grid, right: multi && finalsSeparate && spec.type === "line" ? 96 : 24 },
      xAxis: horizontal ? valAxis : catAxis,
      yAxis: horizontal ? catAxis : valAxis,
      tooltip: {
        ...tooltipBase(t),
        trigger: spec.type === "line" ? "axis" : "item",
        axisPointer: spec.type === "line" ? { type: "line", lineStyle: { color: t.axis, width: 1, type: "solid" } } : { type: "none" },
        formatter: (p: unknown) => (spec.type === "line" ? axisTooltip(p as AxisParam[], t, fmt) : itemTooltip(p as ItemParam, t, fmt)),
      },
    },
  };
}

function tooltipBase(t: ChartTokens) {
  return {
    confine: true, borderWidth: 1, borderColor: t.grid, backgroundColor: t.surface, padding: [8, 10],
    textStyle: { color: t.text, fontSize: 12 }, extraCssText: "box-shadow:0 4px 14px rgba(0,0,0,.12);border-radius:6px;",
  };
}

// --- Tooltips: nós de DOM com textContent (nomes de séries/categorias vêm de cabeçalhos de CSV = dado não confiável) ---
interface AxisParam { axisValueLabel: string; seriesName: string; value: number | null; color?: string }
interface ItemParam { name: string; seriesName: string; value: number | null; color?: string }

function el(tag: string, css: string, text?: string): HTMLElement {
  const e = document.createElement(tag);
  e.style.cssText = css;
  if (text !== undefined) e.textContent = text;
  return e;
}

function row(name: string, value: string, color: string, t: ChartTokens): HTMLElement {
  const r = el("div", "display:flex;align-items:center;gap:8px;margin-top:3px;");
  r.appendChild(el("span", `display:inline-block;width:12px;height:2px;border-radius:1px;background:${color};`)); // chave em linha, não caixa
  r.appendChild(el("strong", `color:${t.text};font-variant-numeric:tabular-nums;margin-right:2px;`, value)); // valor lidera
  r.appendChild(el("span", `color:${t.textSecondary};`, name));
  return r;
}

function axisTooltip(params: AxisParam[], t: ChartTokens, fmt: (v: unknown) => string): HTMLElement {
  const box = el("div", "min-width:120px;");
  box.appendChild(el("div", `color:${t.textSecondary};`, params[0]?.axisValueLabel ?? ""));
  for (const p of params) box.appendChild(row(p.seriesName, p.value === null ? "—" : fmt(p.value), p.color ?? t.series[0], t));
  return box;
}

function itemTooltip(p: ItemParam, t: ChartTokens, fmt: (v: unknown) => string): HTMLElement {
  const box = el("div", "min-width:120px;");
  box.appendChild(el("div", `color:${t.textSecondary};`, p.name));
  box.appendChild(row(p.seriesName, p.value === null ? "—" : fmt(p.value), p.color ?? t.series[0], t));
  return box;
}

function pointTooltip(series: string, xName: string, x: number, y: number, color: string, t: ChartTokens, fmt: (v: unknown) => string): HTMLElement {
  const box = el("div", "min-width:120px;");
  box.appendChild(row(series, fmt(y), color, t));
  box.appendChild(el("div", `color:${t.textSecondary};margin-top:3px;`, `${xName}: ${fmt(x)}`));
  return box;
}

/**
 * Gráfico salvo vs. resultado atual da consulta: se o SQL mudou e as colunas do gráfico sumiram,
 * volta à sugestão automática (em vez de desenhar vazio ou quebrar). Devolve o mesmo objeto quando ainda vale.
 */
export function reconcile(chart: ChartSpec | null, result: QueryResult): ChartSpec | null {
  const names = new Set(result.columns.map((c) => c.name));
  const valid = chart !== null && names.has(chart.x) && chart.ys.length > 0 && chart.ys.every((y) => names.has(y));
  return valid ? chart : suggestSpec(result);
}
