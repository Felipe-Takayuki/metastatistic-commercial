import { useCallback, useState } from "react";
import type { Dataset } from "../api";
import { ANALYSES, defaultState, getDef, problems, resolveState, toOptions, type FormState } from "../lib/analyses";
import { AnalysisForm } from "./AnalysisForm";
import { AnalysisRun } from "./AnalysisRun";

export function AnalysisTab({ dataset }: { dataset: Dataset }) {
  const [defId, setDefId] = useState(ANALYSES[0].id);
  const [states, setStates] = useState<Record<string, FormState>>({}); // cada análise guarda o que o usuário escolheu
  const [submitted, setSubmitted] = useState<{ analysis: string; options: Record<string, unknown> } | null>(null);
  const def = getDef(defId)!;
  const state = states[defId] ?? defaultState(def);
  const resolved = resolveState(def, dataset, state);
  const issues = problems(def, dataset, resolved);

  const onChange = useCallback((s: FormState) => setStates((all) => ({ ...all, [defId]: s })), [defId]);

  return (
    <div className="analysis-grid">
      <div className="card card-pad form-stack">
        <div className="analysis-picker" role="tablist" aria-label="Análise">
          {ANALYSES.map((d) => (
            <button key={d.id} role="tab" aria-selected={d.id === defId} onClick={() => { setDefId(d.id); setSubmitted(null); }}>{d.title}</button>
          ))}
        </div>
        <div>
          <h2 style={{ fontSize: 15 }}>{def.title}</h2>
          <p className="muted small" style={{ margin: "4px 0 0" }}>{def.description}</p>
        </div>
        <AnalysisForm key={defId} def={def} dataset={dataset} state={state} onChange={onChange} />
        <button className="btn primary" disabled={issues.length > 0} onClick={() => setSubmitted({ analysis: def.id, options: toOptions(def, resolved) })}>
          Executar análise
        </button>
      </div>
      <div className="card card-pad" style={{ minHeight: 200 }} aria-live="polite">
        {submitted ? <AnalysisRun analysis={submitted.analysis} datasetId={dataset.id} options={submitted.options} /> : <div className="empty"><h2>Resultados aparecem aqui</h2>Escolha as variáveis e execute a análise.</div>}
      </div>
    </div>
  );
}
