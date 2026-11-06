import type { Dataset, Measure, MeasureFn, QueryBuilder } from "../api";
import { builderProblem, defaultBuilder, isNumeric, MAX_MEASURES, MEASURE_LABEL, repair } from "../lib/builder";

interface Props {
  kind: "chart" | "kpi";
  builder: QueryBuilder;
  datasets: Dataset[];
  onChange: (b: QueryBuilder) => void;
}

/** Montador "sem SQL": dataset, o que mostrar, categorias e cálculos. O SQL é gerado pelo componente pai. */
export function QueryBuilderForm({ kind, builder, datasets, onChange }: Props) {
  const ds = datasets.find((d) => d.id === builder.dataset_id);
  const numeric = ds?.columns.filter(isNumeric) ?? [];
  const problem = builderProblem(builder, ds, kind);
  const points = builder.kind === "points";

  const setKind = (next: "summary" | "points") => {
    if (!ds || next === builder.kind) return;
    if (next === "summary") return onChange(defaultBuilder("chart", ds));
    const [x, y] = [numeric[0]?.name ?? "", numeric[1]?.name ?? numeric[0]?.name ?? ""];
    onChange({ ...builder, kind: "points", group_by: x, measures: [{ fn: "value", column: y }] });
  };
  const setMeasure = (i: number, patch: Partial<Measure>) => onChange({ ...builder, measures: builder.measures.map((m, j) => (j === i ? { ...m, ...patch } : m)) });
  const setFn = (i: number, fn: MeasureFn) => {
    const m = builder.measures[i];
    const keep = ds?.columns.find((c) => c.name === m.column);
    const needsNumber = fn !== "count" && fn !== "min" && fn !== "max";
    const column = fn === "count" ? "" : keep && (!needsNumber || isNumeric(keep)) ? m.column : (needsNumber ? numeric : ds?.columns ?? [])[0]?.name ?? "";
    setMeasure(i, { fn, column });
  };

  return (
    <div className="builder">
      <label className="field">Dataset
        <select value={builder.dataset_id} aria-label="Dataset" onChange={(e) => { const next = datasets.find((d) => d.id === e.target.value); if (next) onChange(repair(builder, next, kind)); }}>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      {kind === "chart" && (
        <label className="field">O que mostrar
          <select value={builder.kind} aria-label="O que mostrar" onChange={(e) => setKind(e.target.value as "summary" | "points")}>
            <option value="summary">Um valor resumido por categoria (barras ou linhas)</option>
            <option value="points">Cada linha como um ponto (dispersão entre dois números)</option>
          </select>
        </label>
      )}
      {kind === "chart" && (
        <label className="field">{points ? "Eixo X (número)" : "Categorias (uma barra por valor de…)"}
          <select value={builder.group_by} aria-label={points ? "Eixo X" : "Categorias"} onChange={(e) => onChange({ ...builder, group_by: e.target.value })}>
            {(points ? numeric : ds?.columns ?? []).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </label>
      )}
      <span className="small muted">{points ? "Eixo Y (número):" : kind === "kpi" ? "Número a mostrar:" : "Valores (até 3):"}</span>
      {builder.measures.map((m, i) => (
        <div key={i} className="condition-row">
          {!points && (
            <select value={m.fn} aria-label={`Cálculo ${i + 1}`} onChange={(e) => setFn(i, e.target.value as MeasureFn)}>
              {Object.entries(MEASURE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
          {m.fn !== "count" && (
            <select value={m.column} aria-label={`Coluna do cálculo ${i + 1}`} onChange={(e) => setMeasure(i, { column: e.target.value })}>
              {(m.fn === "min" || m.fn === "max" ? ds?.columns ?? [] : numeric).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          )}
          {kind === "chart" && !points && builder.measures.length > 1 && (
            <button type="button" className="btn ghost sm" onClick={() => onChange({ ...builder, measures: builder.measures.filter((_, j) => j !== i) })} aria-label={`Remover valor ${i + 1}`}>✕</button>
          )}
        </div>
      ))}
      {kind === "chart" && builder.measures.length < MAX_MEASURES && (
        <div><button type="button" className="btn ghost sm" onClick={() => onChange({ ...builder, measures: [...builder.measures, points ? { fn: "value", column: numeric[0]?.name ?? "" } : numeric[0] ? { fn: "mean", column: numeric[0].name } : { fn: "count", column: "" }] })}>+ valor</button></div>
      )}
      {problem && <p className="muted small" role="status" style={{ margin: 0 }}>Falta: {problem}.</p>}
    </div>
  );
}

/** Alterna entre "Montar sem SQL" e "Escrever SQL" e mostra o SQL gerado (só leitura) no modo sem SQL. */
export function SourceMode({ builderOn, canBuild, sql, onBuilder, onSql }: { builderOn: boolean; canBuild: boolean; sql: string; onBuilder: () => void; onSql: () => void }) {
  return (
    <>
      <div className="toolbar" role="group" aria-label="Como definir os dados">
        <button type="button" className={`btn sm${builderOn ? " primary" : ""}`} aria-pressed={builderOn} onClick={onBuilder} disabled={!canBuild}>Montar sem SQL</button>
        <button type="button" className={`btn sm${builderOn ? "" : " primary"}`} aria-pressed={!builderOn} onClick={onSql}>Escrever SQL</button>
      </div>
      {builderOn && sql && (
        <details className="data-details">
          <summary>Ver o SQL gerado</summary>
          <pre className="tf-sql" aria-label="SQL gerado">{sql}</pre>
        </details>
      )}
    </>
  );
}
