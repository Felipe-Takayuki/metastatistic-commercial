import { useEffect, useState } from "react";
import { api, type AnalysisResponse, type AnalysisStatus } from "../api";
import { useRemote } from "../lib/remote";
import { assumptionNotes, assumptionOptions } from "../lib/assumptions";
import { ResultView } from "./ResultView";

/** true depois de `ms` ativo contínuo (para avisar quando algo demora mais que o normal). */
function useAfter(active: boolean, ms: number): boolean {
  const [late, setLate] = useState(false);
  useEffect(() => {
    if (!active) { setLate(false); return; }
    const t = setTimeout(() => setLate(true), ms);
    return () => clearTimeout(t);
  }, [active, ms]);
  return late;
}

/** Enquanto a análise demora, consulta a situação do motor a cada 2 s (workers ocupados e fila). */
function useEngineStatus(active: boolean): AnalysisStatus | null {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  useEffect(() => {
    if (!active) { setStatus(null); return; }
    let stop = false;
    const tick = () => api.analysisStatus().then((s) => !stop && setStatus(s)).catch(() => {});
    tick();
    const t = setInterval(tick, 2000);
    return () => { stop = true; clearInterval(t); };
  }, [active]);
  return status;
}

function busyMessage(s: AnalysisStatus | null): string {
  if (!s) return "Ainda calculando…";
  const parts = [`${s.busy} de ${s.workers} ${s.workers === 1 ? "motor ocupado" : "motores ocupados"}`];
  if (s.queued > 0) parts.push(`${s.queued} ${s.queued === 1 ? "análise" : "análises"} na fila`);
  if (s.down > 0) parts.push(`${s.down} fora do ar`);
  return `Ainda calculando… ${parts.join(", ")}. Cada motor executa uma análise por vez.`;
}

interface Props {
  analysis: string;
  datasetId: string;
  options: Record<string, unknown>;
  /** Mostra avisos de pressupostos (normalidade, homogeneidade) verificados em segundo plano. */
  assumptions?: boolean;
}

/** Avisos de pressupostos: roda de novo, DEPOIS da análise principal, as mesmas opções + os testes de pressuposto. Falha em silêncio. */
function AssumptionNotes({ analysis, datasetId, options }: { analysis: string; datasetId: string; options: Record<string, unknown> }) {
  const checked = assumptionOptions(analysis, options);
  const key = checked ? `an:${analysis}:${datasetId}:${JSON.stringify(checked)}` : null;
  const { data } = useRemote<AnalysisResponse>(key, () => api.runAnalysis(analysis, datasetId, checked!));
  if (!data || data.status !== "complete") return null;
  const notes = assumptionNotes(analysis, data.results);
  if (notes.length === 0) return null;
  return (
    <div role="status" aria-label="Verificação de pressupostos" style={{ display: "grid", gap: 6, marginBottom: 12 }}>
      {notes.map((n, i) => (
        <div key={i} className={n.level === "warn" ? "alert warn" : "alert info"}>
          {n.level === "warn" ? <strong>Atenção: </strong> : null}{n.text}
        </div>
      ))}
    </div>
  );
}

/** Executa a análise (com cache) e mostra tabelas/gráficos do JASP, ou o erro de forma legível. */
export function AnalysisRun({ analysis, datasetId, options, assumptions = false }: Props) {
  const key = datasetId ? `an:${analysis}:${datasetId}:${JSON.stringify(options)}` : null;
  const { data, error, loading } = useRemote<AnalysisResponse>(key, () => api.runAnalysis(analysis, datasetId, options));

  const slow = useAfter(loading && !data, 8000);
  const engine = useEngineStatus(slow);

  if (error) {
    // o dataset foi excluído depois que a análise foi salva (relatório/dashboard): mensagem útil em vez do erro cru da API
    const gone = /dataset not found/i.test(error);
    return <div className="alert" role="alert">{gone ? "O dataset desta análise foi excluído. Abra o modo de edição e escolha outro." : error}</div>;
  }
  if (!data)
    return (
      <div className="empty" role="status">
        {loading && <span className="spinner" aria-label="Calculando" />}
        {slow && <p className="muted small" style={{ margin: "10px auto 0", maxWidth: 420 }}>{busyMessage(engine)}</p>}
      </div>
    );
  if (data.status !== "complete") {
    const msg = typeof data.results.errorMessage === "string" ? data.results.errorMessage : null;
    return <div className="alert" role="alert">A análise não pôde ser concluída{msg ? `: ${msg}` : ` (${data.status}).`}</div>;
  }
  return (
    <div style={{ opacity: loading ? 0.5 : 1, transition: "opacity .15s" }}>
      {assumptions && !loading && <AssumptionNotes analysis={analysis} datasetId={datasetId} options={options} />}
      <ResultView results={data.results} />
    </div>
  );
}
