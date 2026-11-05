import { useEffect, useMemo, useRef, useState } from "react";
import { type AnalysisTile, type ChartTile, type Dataset, type KpiTile, type TextTile, type Tile } from "../../api";
import { getDef } from "../../lib/analyses";
import { reconcile } from "../../lib/chartSpec";
import { formatKpi } from "../../lib/dashboard";
import { renderMarkdown } from "../../lib/markdown";
import { ChartView } from "../ChartView";
import { DataTable } from "../DataTable";
import { useParams, useTileQuery } from "./params";
import { AnalysisBlockEditor, AnalysisBlockView } from "../report/AnalysisBlock";
import { ChartBlockEditor } from "../report/ChartBlock";
import { SqlEditor } from "../SqlEditor";
import { TextBlockEditor } from "../report/TextBlock";


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
  const { data, error, loading } = useTileQuery(tile.sql);
  const { values, setValue } = useParams();
  const param = tile.click_param;
  // Clicar na mesma categoria de novo limpa o filtro (alterna).
  const onPointClick = param ? (name: string) => setValue(param, values[param] === name ? "" : name) : undefined;
  const spec = useMemo(() => (data ? reconcile(tile.chart, data) : null), [data, tile.chart]);
  const [ref, h] = useBoxHeight();
  return (
    <div ref={ref} className="tile-fill">
      {!tile.sql.trim() && <div className="alert info small">Este tile ainda não tem uma consulta SQL.</div>}
      {error && <div className="alert small" role="alert">{error}</div>}
      {data && h > 0 && (spec ? <ChartView result={data} spec={spec} showTitle={false} height={Math.max(80, h)} onPointClick={onPointClick} /> : <DataTable columns={data.columns} rows={data.rows} maxRows={50} />)}
      {!data && loading && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
    </div>
  );
}

function KpiTileBody({ tile }: { tile: KpiTile }) {
  const { data, error, loading } = useTileQuery(tile.sql);
  if (!tile.sql.trim()) return <div className="alert info small">Este tile ainda não tem uma consulta SQL.</div>;
  if (error) return <div className="alert small" role="alert">{error}</div>;
  if (!data && loading) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;
  return <div className="kpi-value" aria-label={`${tile.title || "Valor"}: ${formatKpi(data, tile)}`}>{formatKpi(data, tile)}</div>;
}

export function TileBody({ tile }: { tile: Tile }) {
  if (tile.type === "text") return <div className="markdown tile-text">{renderMarkdown(tile.markdown)}</div>;
  if (tile.type === "chart") return <ChartTileBody tile={tile} />;
  if (tile.type === "analysis") return <AnalysisBlockView block={tile} />;
  return <KpiTileBody tile={tile} />;
}

export const TILE_LABEL: Record<Tile["type"], string> = { text: "Texto", chart: "Gráfico", kpi: "KPI", analysis: "Análise" };

export function tileHeading(t: Tile): string {
  return t.type === "text" ? "" : t.type === "analysis" ? (getDef(t.analysis)?.title ?? "Análise") : t.title;
}

function KpiEditor({ tile, onChange }: { tile: KpiTile; onChange: (t: KpiTile) => void }) {
  const [ran, setRan] = useState(tile.sql);
  const { data, error } = useTileQuery(ran);
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
export function TileEditor({ tile, onChange, datasets }: { tile: Tile; onChange: (t: Tile) => void; datasets: Dataset[] }) {
  if (tile.type === "analysis") {
    return (
      <>
        <AnalysisBlockEditor block={tile} datasets={datasets} onChange={(b) => onChange({ ...tile, ...b } as AnalysisTile)} />
        <p className="muted small" style={{ margin: 0 }}>Os filtros do dashboard não se aplicam às análises: elas usam o dataset inteiro.</p>
      </>
    );
  }
  if (tile.type === "text") return <TextBlockEditor block={tile} onChange={(b) => onChange({ ...tile, ...b } as TextTile)} />;
  if (tile.type === "chart") return <ChartTileEditor tile={tile} onChange={onChange} />;
  return <KpiEditor tile={tile} onChange={onChange} />;
}

function ChartTileEditor({ tile, onChange }: { tile: ChartTile; onChange: (t: Tile) => void }) {
  const { filters, resolve } = useParams();
  return (
    <>
      <ChartBlockEditor block={tile} resolve={resolve} onChange={(b) => onChange({ ...tile, ...b } as ChartTile)} />
      <label className="field">Ao clicar numa barra ou ponto, definir o filtro
        <select value={tile.click_param ?? ""} onChange={(e) => onChange({ ...tile, click_param: e.target.value || null })} disabled={filters.length === 0}>
          <option value="">— nenhum (gráfico sem cross-filter)</option>
          {filters.map((f) => <option key={f.name} value={f.name}>{f.label || f.name} ({`{{${f.name}}}`})</option>)}
        </select>
        {filters.length === 0 && <span className="muted small">Crie um filtro em “Filtros do dashboard” para usar o cross-filter.</span>}
      </label>
    </>
  );
}
