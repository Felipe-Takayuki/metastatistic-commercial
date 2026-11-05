import { describe, expect, it } from "vitest";
import type { QueryResult, Tile } from "../api";
import { applyLayout, formatKpi, newTile, nextLayout, readingOrder, toGrid } from "./dashboard";

const text = (id: string, x: number, y: number, w = 4, h = 2): Tile => ({ type: "text", id, markdown: "", layout: { x, y, w, h } });
const q = (rows: unknown[][]): QueryResult => ({ columns: [{ name: "v", dtype: "DOUBLE" }], rows, row_count: rows.length, truncated: false, elapsed_ms: 1 });

describe("nextLayout / newTile", () => {
  it("o primeiro tile vai para o topo; os seguintes, abaixo do último", () => {
    expect(nextLayout([], "kpi")).toEqual({ x: 0, y: 0, w: 3, h: 2 });
    expect(nextLayout([text("a", 0, 0, 4, 2), text("b", 4, 3, 4, 4)], "chart")).toEqual({ x: 0, y: 7, w: 6, h: 6 });
  });
  it("id novo e único, com SQL de partida a partir do 1º dataset (aspas escapadas)", () => {
    const ds = [{ id: "d", name: "n", table_name: 'a"b', n_rows: 1, columns: [], created_at: "" }];
    const t = newTile("kpi", [text("a", 0, 0)], ds);
    expect(t.id).not.toBe("a");
    expect(t.type === "kpi" && t.sql).toBe('SELECT count(*) FROM "a""b"');
    expect(newTile("chart", [], []).type === "chart" && (newTile("chart", [], []) as { sql: string }).sql).toBe("");
  });
});

describe("applyLayout", () => {
  const tiles = [text("a", 0, 0), text("b", 4, 0)];
  it("sem mudança devolve a mesma referência (nada de salvar à toa)", () => {
    expect(applyLayout(tiles, toGrid(tiles))).toBe(tiles);
  });
  it("atualiza só o tile que mudou, preservando o conteúdo", () => {
    const out = applyLayout(tiles, [{ i: "a", x: 0, y: 0, w: 4, h: 2 }, { i: "b", x: 8, y: 2, w: 4, h: 3 }]);
    expect(out).not.toBe(tiles);
    expect(out[0]).toBe(tiles[0]);
    expect(out[1]).toEqual({ ...tiles[1], layout: { x: 8, y: 2, w: 4, h: 3 } });
  });
  it("ignora ids desconhecidos na grade", () => {
    expect(applyLayout(tiles, [{ i: "zzz", x: 1, y: 1, w: 1, h: 1 }])).toBe(tiles);
  });
});

describe("readingOrder", () => {
  it("de cima para baixo e da esquerda para a direita, sem mutar a lista", () => {
    const tiles = [text("c", 0, 5), text("b", 6, 0), text("a", 0, 0)];
    expect(readingOrder(tiles).map((t) => t.id)).toEqual(["a", "b", "c"]);
    expect(tiles.map((t) => t.id)).toEqual(["c", "b", "a"]);
  });
});

describe("formatKpi", () => {
  const f = { decimals: 2, prefix: "R$ ", suffix: "" };
  it("número em pt-BR com as casas pedidas", () => {
    expect(formatKpi(q([[1234567.891]]), f)).toBe("R$ 1.234.567,89");
    expect(formatKpi(q([[7]]), { decimals: 0, prefix: "", suffix: " %" })).toBe("7 %");
  });
  it("sem linhas, nulo ou sem resultado: traço; texto passa como está; não finito não vira número", () => {
    expect(formatKpi(undefined, f)).toBe("—");
    expect(formatKpi(q([]), f)).toBe("—");
    expect(formatKpi(q([[null]]), f)).toBe("—");
    expect(formatKpi(q([["Sul"]]), { decimals: 0, prefix: "", suffix: "" })).toBe("Sul");
    expect(formatKpi(q([[Infinity]]), { decimals: 0, prefix: "", suffix: "" })).toBe("Infinity");
  });
});
