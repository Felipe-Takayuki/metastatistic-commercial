import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Dataset, type TransformPreview } from "../api";
import { cleanStep, defaultStep, describeStep, failingStep, moveStep, stepProblem, STEP_KINDS, type ColumnInfo, type Step, type StepOp } from "../lib/transforms";
import { useCan } from "./AuthGate";
import { DataTable } from "./DataTable";
import { StepForm } from "./transform/StepForm";

export interface TransformDraft { sourceId: string; steps: Step[] }
export const newDraft = (sourceId: string): TransformDraft => ({ sourceId, steps: [] });

interface Props {
  dataset: Dataset;
  datasets: Dataset[];
  draft: TransformDraft;
  onDraft: (d: TransformDraft) => void;
  onDatasetCreated: (ds: Dataset) => void | Promise<void>;
}

const GROUPS = ["Colunas", "Linhas", "Nova coluna", "Por grupo e janela", "Reformatar e combinar"] as const;

export function TransformTab({ dataset, datasets, draft, onDraft, onDatasetCreated }: Props) {
  const canEdit = useCan("editor");
  const source = datasets.find((d) => d.id === draft.sourceId) ?? dataset;
  const [preview, setPreview] = useState<TransformPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<{ index: number | null; step: Step } | null>(null); // index null = passo novo
  const [showSql, setShowSql] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [recipeNote, setRecipeNote] = useState<{ sourceId: string; steps: Step[]; count: number } | null>(null);
  const seq = useRef(0);

  // a prévia reexecuta a receita inteira a cada mudança (debounce): o servidor é a fonte de verdade dos tipos e dos erros
  useEffect(() => {
    const mine = ++seq.current;
    setLoading(true);
    const t = setTimeout(() => {
      api.transformPreview({ source_id: draft.sourceId, steps: draft.steps.map(cleanStep) }).then(
        (p) => { if (mine === seq.current) { setPreview(p); setError(null); setLoading(false); } },
        (e) => { if (mine === seq.current) { setError((e as Error).message); setLoading(false); } },
      );
    }, 250);
    return () => clearTimeout(t);
  }, [draft]);

  // este dataset veio de uma receita? Oferece reabri-la
  useEffect(() => {
    let cancelled = false;
    setRecipeNote(null);
    api.getRecipe(dataset.id).then((r) => { if (!cancelled && r) setRecipeNote({ sourceId: r.recipe.source_id, steps: r.recipe.steps, count: r.recipe.steps.length }); }, () => undefined);
    return () => { cancelled = true; };
  }, [dataset.id]);

  const baseCols: ColumnInfo[] = source.columns.map((c) => ({ name: c.name, dtype: c.dtype }));
  /** Colunas disponíveis ANTES do passo `index` (ou depois do último, para um passo novo). */
  const colsBefore = (index: number | null): ColumnInfo[] => {
    const schemas = preview?.schemas;
    const at = index ?? draft.steps.length;
    return schemas && schemas[at] && !(error && at >= (failingStep(error) ?? Infinity)) ? schemas[at] : (schemas?.[Math.min(at, schemas.length - 1)] ?? baseCols);
  };
  const failing = failingStep(error);

  const setSteps = (steps: Step[]) => onDraft({ ...draft, steps });
  const startNew = (op: StepOp) => setEditing({ index: null, step: defaultStep(op, colsBefore(null), datasets.find((d) => d.id !== draft.sourceId)?.id ?? "") });
  const apply = () => {
    if (!editing) return;
    const step = cleanStep(editing.step);
    setSteps(editing.index === null ? [...draft.steps, step] : draft.steps.map((s, i) => (i === editing.index ? step : s)));
    setEditing(null);
  };
  const editingCols = editing ? colsBefore(editing.index) : baseCols;
  const problem = editing ? stepProblem(editing.step, editingCols, editing.index === null ? undefined : draft.steps[editing.index]) : null;

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const created = await api.transformSave({ source_id: draft.sourceId, steps: draft.steps.map(cleanStep) }, saveName.trim());
      onDraft(newDraft(created.id)); // o rascunho recomeça sobre o dataset novo
      setSaveName("");
      await onDatasetCreated(created);
    } catch (e) {
      setSaveError((e as Error).message);
      setSaving(false);
      if (e instanceof ApiError && e.status === 401) return;
    }
  };

  const reopen = () => {
    if (!recipeNote) return;
    if (!datasets.some((d) => d.id === recipeNote.sourceId)) return setError("O dataset de origem desta receita não existe mais (ou você não tem acesso a ele).");
    onDraft({ sourceId: recipeNote.sourceId, steps: recipeNote.steps });
    setRecipeNote(null);
  };

  return (
    <div className="tf-layout">
      <section className="tf-main" aria-label="Prévia do resultado">
        {recipeNote && draft.steps.length === 0 && (
          <div className="alert" role="note" style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span style={{ flex: 1 }}>Este dataset foi criado por uma receita de {recipeNote.count} {recipeNote.count === 1 ? "passo" : "passos"}.</span>
            <button className="btn sm" onClick={reopen}>Reabrir receita</button>
          </div>
        )}
        <div className="tf-head">
          <h2 style={{ fontSize: 15, margin: 0 }}>Resultado</h2>
          {loading && <span className="spinner" aria-label="Atualizando a prévia" />}
          {preview && !error && <span className="muted small" data-testid="tf-summary">{preview.total_rows.toLocaleString("pt-BR")} linhas · {preview.columns.length} colunas{preview.truncated ? ` · prévia das primeiras ${preview.row_count}` : ""}</span>}
          <span className="spacer" />
          {preview && <button className="btn ghost sm" onClick={() => setShowSql((v) => !v)} aria-expanded={showSql}>{showSql ? "Ocultar SQL" : "Ver SQL"}</button>}
        </div>
        {error && <div className="alert" role="alert">{error}</div>}
        {showSql && preview && <pre className="tf-sql" aria-label="SQL gerado">{preview.sql.replace(/, __s/g, ",\n  __s")}</pre>}
        {preview && <div style={{ opacity: error ? 0.5 : 1 }}><DataTable columns={preview.columns} rows={preview.rows} /></div>}
        {!preview && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      </section>

      <aside className="tf-steps" aria-label="Passos aplicados">
        <h2 style={{ fontSize: 15, margin: "0 0 8px" }}>Passos aplicados</h2>
        <ol className="step-list">
          <li className="step origin"><span className="step-text">Origem: <strong>{source.name}</strong></span></li>
          {draft.steps.map((s, i) => (
            <li key={i} className={`step${failing === i + 1 ? " failing" : failing !== null && i + 1 > failing ? " skipped" : ""}`}>
              <span className="step-n">{i + 1}</span>
              <span className="step-text">{describeStep(s, (id) => datasets.find((d) => d.id === id)?.name ?? "dataset removido")}</span>
              <span className="step-actions">
                <button className="btn ghost sm" onClick={() => setSteps(moveStep(draft.steps, i, -1))} disabled={i === 0} aria-label={`Subir passo ${i + 1}`}>↑</button>
                <button className="btn ghost sm" onClick={() => setSteps(moveStep(draft.steps, i, 1))} disabled={i === draft.steps.length - 1} aria-label={`Descer passo ${i + 1}`}>↓</button>
                <button className="btn ghost sm" onClick={() => setEditing({ index: i, step: s })} aria-label={`Editar passo ${i + 1}`}>✎</button>
                <button className="btn ghost sm" onClick={() => setSteps(draft.steps.filter((_, j) => j !== i))} aria-label={`Remover passo ${i + 1}`}>✕</button>
              </span>
            </li>
          ))}
        </ol>
        {draft.steps.length === 0 && <p className="muted small">Cada transformação vira um passo. Os dados originais não mudam: o resultado só vira dataset quando você salvar.</p>}
        <select className="add-step" value="" aria-label="Adicionar passo" onChange={(e) => e.target.value && startNew(e.target.value as StepOp)}>
          <option value="">+ Adicionar passo…</option>
          {GROUPS.map((g) => <optgroup key={g} label={g}>{STEP_KINDS.filter((k) => k.group === g).map((k) => <option key={k.op} value={k.op}>{k.label}</option>)}</optgroup>)}
        </select>
        {draft.steps.length > 0 && <button className="btn ghost sm" onClick={() => setSteps([])} style={{ marginTop: 6 }}>Desfazer todos os passos</button>}

        <div className="tf-save">
          <h3 style={{ fontSize: 14, margin: "14px 0 6px" }}>Salvar</h3>
          {canEdit ? (
            <>
              <input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder={`${source.name.replace(/\.csv$/i, "")} (transformado)`} maxLength={120} aria-label="Nome do novo dataset" />
              <button className="btn primary" onClick={save} disabled={saving || !!error || draft.steps.length === 0 || !saveName.trim()} style={{ marginTop: 6 }}>{saving ? <span className="spinner" /> : null} Salvar como dataset</button>
              {saveError && <div className="alert" role="alert" style={{ marginTop: 6 }}>{saveError}</div>}
              <p className="muted small" style={{ margin: "6px 0 0" }}>Cria um dataset novo, analisável e consultável por SQL. Se a origem tiver acesso restrito ou filtro de linhas, o novo herda a restrição.</p>
            </>
          ) : <p className="muted small">Só editores e administradores salvam datasets.</p>}
        </div>
      </aside>

      {editing && (
        <div className="modal-backdrop" onKeyDown={(e) => e.key === "Escape" && setEditing(null)}>
          <div className="modal card" style={{ maxWidth: 620 }} role="dialog" aria-modal="true" aria-label={editing.index === null ? "Novo passo" : `Editar passo ${editing.index + 1}`}>
            <div className="modal-head"><strong>{STEP_KINDS.find((k) => k.op === editing.step.op)?.label}</strong><span className="spacer" /><button className="btn ghost sm" onClick={() => setEditing(null)} aria-label="Fechar">✕</button></div>
            <div className="modal-body">
              <StepForm step={editing.step} cols={editingCols} datasets={datasets} currentId={draft.sourceId} onChange={(step) => setEditing({ ...editing, step })} />
              {problem && <p className="muted small" role="status" style={{ margin: 0 }}>Falta: {problem}.</p>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn primary" onClick={apply} disabled={!!problem}>{editing.index === null ? "Adicionar passo" : "Aplicar"}</button>
                <button className="btn" onClick={() => setEditing(null)}>Cancelar</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
