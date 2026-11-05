import type { Dataset, KpiTile, QueryResult, Tile, TileLayout } from "../api";
import { newId } from "./blocks";

export const GRID_COLS = 12;
export const ROW_HEIGHT = 56;
export const GRID_GAP = 12;
export const STACK_BELOW = 720; // abaixo desta largura (px) os tiles empilham em coluna única

export type TileType = Tile["type"];
const SIZE: Record<TileType, { w: number; h: number }> = { kpi: { w: 3, h: 2 }, chart: { w: 6, h: 6 }, text: { w: 6, h: 3 } };

/** Primeira posição livre: nova linha abaixo de tudo, na coluna 0 (a compactação vertical sobe o tile se houver espaço). */
export function nextLayout(tiles: Tile[], type: TileType): TileLayout {
  const y = tiles.reduce((m, t) => Math.max(m, t.layout.y + t.layout.h), 0);
  return { x: 0, y, ...SIZE[type] };
}

export function newTile(type: TileType, tiles: Tile[], datasets: Dataset[]): Tile {
  const id = newId(tiles.map((t) => t.id));
  const layout = nextLayout(tiles, type);
  const table = datasets[0]?.table_name;
  if (type === "text") return { type, id, markdown: "", layout };
  if (type === "kpi") return { type, id, title: "", sql: table ? `SELECT count(*) FROM "${table.replace(/"/g, '""')}"` : "", decimals: 0, prefix: "", suffix: "", layout };
  return { type, id, title: "", sql: table ? `SELECT * FROM "${table.replace(/"/g, '""')}" LIMIT 20` : "", chart: null, layout };
}

export interface GridItem { i: string; x: number; y: number; w: number; h: number }

export const toGrid = (tiles: Tile[]): GridItem[] => tiles.map((t) => ({ i: t.id, ...t.layout }));

/**
 * Aplica ao estado as posições devolvidas pela grade. Devolve a MESMA lista (mesma referência) quando nada mudou, para que
 * o disparo inicial da grade (que normaliza/compacta) e re-renders não marquem o dashboard como "alterado" à toa.
 */
export function applyLayout(tiles: Tile[], layout: readonly GridItem[]): Tile[] {
  const byId = new Map(layout.map((l) => [l.i, l]));
  let changed = false;
  const next = tiles.map((t) => {
    const l = byId.get(t.id);
    if (!l) return t;
    const { x, y, w, h } = t.layout;
    if (l.x === x && l.y === y && l.w === w && l.h === h) return t;
    changed = true;
    return { ...t, layout: { x: l.x, y: l.y, w: l.w, h: l.h } } as Tile;
  });
  return changed ? next : tiles;
}

/** Ordem de leitura (de cima para baixo, da esquerda para a direita): usada ao empilhar em tela estreita. */
export const readingOrder = (tiles: Tile[]): Tile[] => tiles.slice().sort((a, b) => a.layout.y - b.layout.y || a.layout.x - b.layout.x);

/** Valor do KPI: 1ª coluna da 1ª linha. Número em pt-BR com as casas pedidas; nulo vira "—"; texto passa como está. */
export function formatKpi(result: QueryResult | undefined, tile: Pick<KpiTile, "decimals" | "prefix" | "suffix">): string {
  if (!result || result.rows.length === 0 || result.columns.length === 0) return "—";
  const v = result.rows[0][0];
  if (v === null || v === undefined) return "—";
  if (typeof v === "number" && Number.isFinite(v)) {
    const n = v.toLocaleString("pt-BR", { minimumFractionDigits: tile.decimals, maximumFractionDigits: tile.decimals });
    return `${tile.prefix}${n}${tile.suffix}`;
  }
  return `${tile.prefix}${String(v)}${tile.suffix}`;
}
