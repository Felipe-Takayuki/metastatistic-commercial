import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ChartTile, type KpiTile, type QueryResult, type TextTile, type Tile } from "../../api";
import { reconcile } from "../../lib/chartSpec";
import { formatKpi } from "../../lib/dashboard";
import { renderMarkdown } from "../../lib/markdown";
import { useRemote } from "../../lib/remote";
import { ChartView } from "../ChartView";
import { DataTable } from "../DataTable";
import { ChartBlockEditor } from "../report/ChartBlock";
import { SqlEditor } from "../SqlEditor";
import { TextBlockEditor } from "../report/TextBlock";

const useQuery = (sql: string) => useRemote<QueryResult>(sql.trim() ? `q:${sql}` : null, () => api.runQuery(sql));

/** Altura útil do corpo do tile (acompanha o redimensionamento ao vivo). */
function useBoxHeight() {
  const ref = useRef<HTMLDivElement>(null);
  const [h, setH] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setH(Math.floor(e.contentRect.height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, h] as const;
}

function ChartTileBody({ tile }: { tile: ChartTile }) {
  const { data, error, loading } = useQuery(tile.sql);
  const spec = useMemo(() => (data ? reconcile(tile.chart, data) : null), [data, tile.chart]);
  const [ref, h] = useBoxHeight();
  return (
    <div ref={ref} className="tile-fill">
      {!tile.sql.trim() && <div className="alert info small">Este tile ainda não tem uma consulta SQL.</div>}
      {error && <div className="alert small" role="alert">{error}</div>}
      {data && h > 0 && (spec ? <ChartView result={data} spec={spec} showTitle={false} height={Math.max(80, h)} /> : <DataTable columns={data.columns} rows={data.rows} maxRows={50} />)}
      {!data && loading && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
    </div>
  );
}

function KpiTileBody({ tile }: { tile: KpiTile }) {
  const { data, error, loading } = useQuery(tile.sql);
  if (!tile.sql.trim()) return <div className="alert info small">Este tile ainda não tem uma consulta SQL.</div>;
  if (error) return <div className="alert small" role="alert">{error}</div>;
  if (!data && loading) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;
  return <div className="kpi-value" aria-label={`${tile.title || "Valor"}: ${formatKpi(data, tile)}`}>{formatKpi(data, tile)}</div>;
}

export function TileBody({ tile }: { tile: Tile }) {
  if (tile.type === "text") return <div className="markdown tile-text">{renderMarkdown(tile.markdown)}</div>;
  if (tile.type === "chart") return <ChartTileBody tile={tile} />;
  return <KpiTileBody tile={tile} />;
}

export const TILE_LABEL: Record<Tile["type"], string> = { text: "Texto", chart: "Gráfico", kpi: "KPI" };

export function tileHeading(t: Tile): string {
  return t.type === "text" ? "" : t.title;
}

function KpiEditor({ tile, onChange }: { tile: KpiTile; onChange: (t: KpiTile) => void }) {
  const [ran, setRan] = useState(tile.sql);
  const { data, error } = useQuery(ran);
  return (
    <>
      <label className="field">Título
        <input type="text" value={tile.title} maxLength={200} onChange={(e) => onChange({ ...tile, title: e.target.value })} placeholder="Ex.: Receita total" />
      </label>
      <SqlEditor value={tile.sql} onChange={(sql) => onChange({ ...tile, sql })} onRun={() => setRan(tile.sql)} height="90px" />
      <div className="toolbar">
        <button className="btn primary sm" onClick={() => setRan(tile.sql)} disabled={!tile.sql.trim()}>▶ Executar</button>
        <span className="muted small">O KPI mostra a 1ª coluna da 1ª linha do resultado.</span>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      <div className="kpi-fields">
        <label className="field">Casas decimais
          <input type="number" min={0} max={6} value={tile.decimals} onChange={(e) => onChange({ ...tile, decimals: Math.min(6, Math.max(0, Math.trunc(Number(e.target.value) || 0))) })} />
        </label>
        <label className="field">Prefixo
          <input type="text" value={tile.prefix} maxLength={10} onChange={(e) => onChange({ ...tile, prefix: e.target.value })} placeholder="R$ " />
        </label>
        <label className="field">Sufixo
          <input type="text" value={tile.suffix} maxLength={10} onChange={(e) => onChange({ ...tile, suffix: e.target.value })} placeholder=" %" />
        </label>
      </div>
      {data && <div className="muted small">Prévia: <strong>{formatKpi(data, tile)}</strong></div>}
    </>
  );
}

/** Editor do conteúdo de um tile (a posição é editada arrastando na grade). */
export function TileEditor({ tile, onChange }: { tile: Tile; onChange: (t: Tile) => void }) {
  if (tile.type === "text") return <TextBlockEditor block={tile} onChange={(b) => onChange({ ...tile, ...b } as TextTile)} />;
  if (tile.type === "chart") return <ChartBlockEditor block={tile} onChange={(b) => onChange({ ...tile, ...b } as ChartTile)} />;
  return <KpiEditor tile={tile} onChange={onChange} />;
}
