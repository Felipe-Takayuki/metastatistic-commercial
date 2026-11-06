import type { EditorView } from "@codemirror/view";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Dataset, type QueryResult } from "../api";
import { suggestSpec, type ChartSpec } from "../lib/chartSpec";
import { useCan } from "./AuthGate";
import { ChartView } from "./ChartView";
import { DataTable } from "./DataTable";
import { SqlEditor } from "./SqlEditor";

const quote = (id: string) => `"${id.replace(/"/g, '""')}"`;
const defaultSql = (ds: Dataset) => `SELECT * FROM ${quote(ds.table_name)} LIMIT 100`;

interface Props {
  dataset: Dataset;
  datasets: Dataset[];
  /** Chamado depois de "Salvar como dataset" (o App recarrega a lista e abre o novo dataset). */
  onDatasetCreated: (ds: Dataset) => void;
}

const stem = (name: string) => name.replace(/\.csv$/i, "");

export function SqlTab({ dataset, datasets, onDatasetCreated }: Props) {
  const canEdit = useCan("editor");
  const [text, setText] = useState(() => defaultSql(dataset));
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [view, setView] = useState<"chart" | "table">("table");
  const [spec, setSpec] = useState<ChartSpec | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const editor = useRef<EditorView | null>(null);
  const textRef = useRef(text);
  textRef.current = text;

  // Trocou de dataset: volta ao SQL padrão dele e limpa o resultado antigo.
  useEffect(() => {
    setText(defaultSql(dataset));
    setResult(null);
    setError(null);
    setSpec(null);
    setSaveOpen(false);
    setSaveError(null);
  }, [dataset.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const r = await api.runQuery(textRef.current);
      const suggested = suggestSpec(r);
      setResult(r);
      setSpec(suggested);
      setView(suggested ? "chart" : "table");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }, []);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      onDatasetCreated(await api.createDatasetFromQuery(saveName.trim(), textRef.current));
      setSaveOpen(false);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const insert = (snippet: string) => {
    const v = editor.current;
    if (!v) return setText((t) => `${t} ${snippet}`);
    const { from, to } = v.state.selection.main;
    v.dispatch({ changes: { from, to, insert: snippet }, selection: { anchor: from + snippet.length } });
    v.focus();
  };

  return (
    <>
      <div className="chips" aria-label="Tabelas e colunas">
        <span className="muted small">Tabelas:</span>
        {datasets.map((d) => <button key={d.id} className="chip btn-chip" onClick={() => insert(quote(d.table_name))} title={d.name}>{d.table_name}</button>)}
      </div>
      <div className="chips">
        <span className="muted small">Colunas de {dataset.table_name}:</span>
        {dataset.columns.map((c) => <button key={c.name} className="chip btn-chip" onClick={() => insert(quote(c.name))}>{c.name}</button>)}
      </div>

      <SqlEditor value={text} onChange={setText} onRun={run} onCreate={(v) => { editor.current = v; }} />
      <div className="toolbar">
        <button className="btn primary" onClick={run} disabled={running || !text.trim()}>
          {running ? <span className="spinner" /> : "▶"} Executar
        </button>
        {canEdit && <button className="btn" onClick={() => { setSaveOpen((o) => !o); setSaveName((n) => n || `${stem(dataset.name)} (derivado)`); }} disabled={!text.trim()} aria-expanded={saveOpen}>
          Salvar como dataset…
        </button>}
        <span className="muted small">Ctrl/⌘ + Enter · somente leitura (SELECT)</span>
        <span className="spacer" />
        {result && <span className="muted small">{result.row_count.toLocaleString("pt-BR")} linhas{result.truncated && " (truncado)"} · {result.elapsed_ms} ms</span>}
      </div>

      {saveOpen && (
        <form className="save-row card card-pad" onSubmit={save}>
          <label className="field" style={{ flex: 1, minWidth: 220 }}>Nome do novo dataset
            <input type="text" value={saveName} onChange={(e) => setSaveName(e.target.value)} maxLength={120} autoFocus />
          </label>
          <button className="btn primary" type="submit" disabled={saving || !saveName.trim()}>{saving ? <span className="spinner" /> : null} Salvar</button>
          <span className="muted small" style={{ flexBasis: "100%" }}>
            Grava o resultado completo desta consulta como um dataset novo (até 2 milhões de linhas), pronto para análises. Use para criar colunas (ex.: bloco) ou aplicar transformações (sqrt, log10).
          </span>
          {saveError && <div className="alert" role="alert" style={{ flexBasis: "100%" }}>{saveError}</div>}
        </form>
      )}

      {error && <div className="alert" role="alert">{error}</div>}

      {result && (
        <div className="card card-pad">
          <div className="tabs" role="tablist" style={{ marginBottom: 14 }}>
            <button className="tab" role="tab" aria-selected={view === "chart"} onClick={() => setView("chart")} disabled={!spec}>Gráfico</button>
            <button className="tab" role="tab" aria-selected={view === "table"} onClick={() => setView("table")}>Tabela</button>
          </div>
          {result.truncated && <div className="alert info" style={{ marginBottom: 12 }}>Resultado truncado no limite do servidor. Filtre ou agregue no SQL para ver tudo.</div>}
          {view === "table" || !spec ? <DataTable columns={result.columns} rows={result.rows} /> : <ChartView result={result} spec={spec} onSpec={setSpec} />}
        </div>
      )}
    </>
  );
}
