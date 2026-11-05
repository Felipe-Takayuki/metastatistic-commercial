import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ChartBlock, type QueryResult } from "../../api";
import { reconcile } from "../../lib/chartSpec";
import type { Resolved } from "../../lib/params";
import { useRemote } from "../../lib/remote";
import { ChartView } from "../ChartView";
import { DataTable } from "../DataTable";
import { SqlEditor } from "../SqlEditor";

const useQuery = (sql: string, resolve?: (sql: string) => Resolved) => {
  const r: Resolved = resolve ? resolve(sql) : { sql };
  const q = useRemote<QueryResult>("sql" in r && r.sql.trim() ? `q:${r.sql}` : null, () => api.runQuery((r as { sql: string }).sql));
  return "error" in r ? { data: undefined, error: r.error, loading: false } : q;
};

function DataDetails({ data }: { data: QueryResult }) {
  // A tabela é o "alívio" de acessibilidade do gráfico (valores completos sem depender de cor ou hover).
  return (
    <details className="no-print data-details">
      <summary>Ver dados ({data.row_count.toLocaleString("pt-BR")} linhas)</summary>
      <DataTable columns={data.columns} rows={data.rows} maxRows={200} />
    </details>
  );
}

export function ChartBlockView({ block }: { block: ChartBlock }) {
  const { data, error, loading } = useQuery(block.sql);
  const spec = useMemo(() => (data ? reconcile(block.chart, data) : null), [data, block.chart]);
  return (
    <div className="report-block">
      {block.title && <h3 className="block-title">{block.title}</h3>}
      {!block.sql.trim() && <div className="alert info">Este bloco ainda não tem uma consulta SQL.</div>}
      {error && <div className="alert" role="alert">{error}</div>}
      {data && (spec ? <ChartView result={data} spec={spec} showTitle={!block.title} vector /> : <DataTable columns={data.columns} rows={data.rows} maxRows={50} />)}
      {data && spec && <DataDetails data={data} />}
      {!data && loading && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
    </div>
  );
}

/** `resolve` (opcional): troca `{{filtros}}` do dashboard pelo valor atual antes de consultar. */
export function ChartBlockEditor({ block, onChange, resolve }: { block: ChartBlock; onChange: (b: ChartBlock) => void; resolve?: (sql: string) => Resolved }) {
  const [ran, setRan] = useState(block.sql); // SQL cujo resultado está na tela
  const { data, error, loading } = useQuery(ran, resolve);
  const blockRef = useRef(block);
  blockRef.current = block;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Ao chegar um resultado, reconcilia o gráfico salvo com as colunas atuais.
  useEffect(() => {
    if (!data) return;
    const next = reconcile(blockRef.current.chart, data);
    if (JSON.stringify(next) !== JSON.stringify(blockRef.current.chart)) onChangeRef.current({ ...blockRef.current, chart: next });
  }, [data]);

  const run = () => setRan(blockRef.current.sql);
  const spec = data ? reconcile(block.chart, data) : null;

  return (
    <>
      <label className="field">Título do gráfico
        <input type="text" value={block.title} maxLength={200} onChange={(e) => onChange({ ...block, title: e.target.value })} placeholder="Ex.: Receita média por região" />
      </label>
      <SqlEditor value={block.sql} onChange={(sql) => onChange({ ...block, sql })} onRun={run} height="110px" />
      <div className="toolbar">
        <button className="btn primary sm" onClick={run} disabled={!block.sql.trim() || loading}>{loading ? <span className="spinner" /> : "▶"} Executar</button>
        {ran !== block.sql && <span className="muted small">SQL alterado: execute para atualizar o gráfico.</span>}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {data && (spec ? <ChartView result={data} spec={spec} onSpec={(s) => onChange({ ...block, chart: s })} showTitle={!block.title} vector /> : <DataTable columns={data.columns} rows={data.rows} maxRows={50} />)}
      {data && spec && <DataDetails data={data} />}
    </>
  );
}
