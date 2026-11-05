import { useState } from "react";
import type { AnalysisBlock, Dataset } from "../../api";
import { ANALYSES, defaultState, fromOptions, getDef, isComplete, problems, resolveState, toOptions, TTEST_DEF, type AnalysisDef, type FormState } from "../../lib/analyses";
import { AnalysisForm } from "../AnalysisForm";
import { AnalysisRun } from "../AnalysisRun";

const freshOptions = (def: AnalysisDef, dataset: Dataset | undefined) => toOptions(def, resolveState(def, dataset, defaultState(def)));

export function AnalysisBlockView({ block }: { block: AnalysisBlock }) {
  const def = getDef(block.analysis);
  if (!def) return <div className="report-block"><div className="alert info">Análise desconhecida: {block.analysis}. Abra o modo de edição e escolha outra.</div></div>;
  if (!block.dataset_id || !isComplete(def, block.options))
    return <div className="report-block"><div className="alert info">Análise incompleta: abra o modo de edição e escolha o dataset e as variáveis.</div></div>;
  return <div className="report-block"><AnalysisRun analysis={block.analysis} datasetId={block.dataset_id} options={block.options} /></div>;
}

interface EditorProps {
  block: AnalysisBlock;
  datasets: Dataset[];
  onChange: (b: AnalysisBlock) => void;
}

export function AnalysisBlockEditor({ block, datasets, onChange }: EditorProps) {
  const dataset = datasets.find((d) => d.id === block.dataset_id);
  const def = getDef(block.analysis) ?? TTEST_DEF;
  const state = fromOptions(def, block.options);
  // Snapshot (análise + dataset + opções) cujo resultado está na tela. Trocar a análise ou o dataset nunca pode
  // reexecutar opções antigas contra outra coisa.
  const snapshot = () => JSON.stringify({ a: block.analysis, d: block.dataset_id, o: block.options });
  const [ran, setRan] = useState<string>(snapshot);
  const current = snapshot();
  const shown = JSON.parse(ran) as { a: string; d: string; o: Record<string, unknown> };
  const shownDef = getDef(shown.a);
  const issues = problems(def, dataset, resolveState(def, dataset, state));

  const changeDataset = (id: string) =>
    onChange({ ...block, dataset_id: id, options: freshOptions(def, datasets.find((d) => d.id === id)) });
  const changeAnalysis = (id: string) => {
    const next = getDef(id)!;
    onChange({ ...block, analysis: id, options: freshOptions(next, dataset) });
  };
  const changeForm = (s: FormState) => onChange({ ...block, options: toOptions(def, resolveState(def, dataset, s)) });

  return (
    <div className="analysis-block">
      <div className="form-stack">
        <label className="field">Análise
          <select value={getDef(block.analysis) ? block.analysis : ""} onChange={(e) => changeAnalysis(e.target.value)}>
            {!getDef(block.analysis) && <option value="">{`(desconhecida: ${block.analysis})`}</option>}
            {ANALYSES.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </select>
        </label>
        <label className="field">Dataset
          <select value={dataset ? block.dataset_id : ""} onChange={(e) => changeDataset(e.target.value)}>
            {!dataset && <option value="">{block.dataset_id ? "(dataset removido)" : "Escolha um dataset"}</option>}
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        {dataset ? (
          <AnalysisForm key={def.id} def={def} dataset={dataset} state={state} onChange={changeForm} />
        ) : (
          <div className="alert info small">{block.dataset_id ? "O dataset desta análise foi excluído. Escolha outro." : "Envie um CSV na aba Explorar para usar aqui."}</div>
        )}
        <div className="toolbar">
          <button className="btn primary sm" disabled={!dataset || issues.length > 0} onClick={() => setRan(current)}>Executar análise</button>
          {ran !== current && issues.length === 0 && <span className="muted small">Opções alteradas: execute para atualizar o resultado.</span>}
        </div>
      </div>
      <div className="analysis-out">
        {shown.d && datasets.some((d) => d.id === shown.d) && shownDef && isComplete(shownDef, shown.o)
          ? <AnalysisRun analysis={shown.a} datasetId={shown.d} options={shown.o} />
          : <div className="muted small">O resultado aparece aqui.</div>}
      </div>
    </div>
  );
}
