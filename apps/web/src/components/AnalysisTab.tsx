import { useCallback } from "react";
import type { Dataset } from "../api";
import { defaultState, groupedAnalyses, getDef, problems, resolveState, toOptions, type AnalysisSession, type FormState } from "../lib/analyses";
import { AnalysisForm } from "./AnalysisForm";
import { AnalysisRun } from "./AnalysisRun";

export function AnalysisTab({ dataset, session, onSession }: { dataset: Dataset; session: AnalysisSession; onSession: (update: (s: AnalysisSession) => AnalysisSession) => void }) {
  const { defId, states, submitted } = session;
  const def = getDef(defId)!;
  const state = states[defId] ?? defaultState(def);
  const resolved = resolveState(def, dataset, state);
  const issues = problems(def, dataset, resolved);

  const onChange = useCallback((st: FormState) => onSession((cur) => ({ ...cur, states: { ...cur.states, [defId]: st } })), [defId, onSession]);

  return (
    <div className="analysis-grid">
      <div className="card card-pad form-stack">
        <div className="analysis-picker" role="tablist" aria-label="Análise">
          {groupedAnalyses().map((g) => (
            <div key={g.title} role="presentation" className="analysis-group">
              <div role="presentation" className="analysis-group-title">{g.title}</div>
              {g.defs.map((d) => (
                <button key={d.id} role="tab" aria-selected={d.id === defId} onClick={() => onSession((cur) => ({ ...cur, defId: d.id, submitted: null }))}>{d.title}</button>
              ))}
            </div>
          ))}
        </div>
        <div>
          <h2 style={{ fontSize: 15 }}>{def.title}</h2>
          <p className="muted small" style={{ margin: "4px 0 0" }}>{def.description}</p>
        </div>
        <AnalysisForm key={defId} def={def} dataset={dataset} state={state} onChange={onChange} />
        <button className="btn primary" disabled={issues.length > 0} onClick={() => onSession((cur) => ({ ...cur, submitted: { analysis: def.id, options: toOptions(def, resolved) } }))}>
          Executar análise
        </button>
      </div>
      <div className="card card-pad" style={{ minHeight: 200 }} aria-live="polite">
        {submitted ? <AnalysisRun analysis={submitted.analysis} datasetId={dataset.id} options={submitted.options} notes /> : <div className="empty"><h2>Resultados aparecem aqui</h2>Escolha as variáveis e execute a análise.</div>}
      </div>
    </div>
  );
}
