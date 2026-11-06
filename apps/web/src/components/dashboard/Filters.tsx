import type { DashFilter } from "../../api";
import { filterProblems, sanitizeName } from "../../lib/params";

/** Barra de filtros: valores atuais (não são salvos; cada visitante filtra do seu jeito). */
export function FilterBar({ filters, values, onChange }: { filters: DashFilter[]; values: Record<string, string>; onChange: (name: string, value: string) => void }) {
  if (filters.length === 0) return null;
  const active = filters.filter((f) => (values[f.name] ?? "") !== "");
  return (
    <div className="filter-bar no-print" role="group" aria-label="Filtros do dashboard">
      {filters.map((f, i) => (
        <label key={`${i}:${f.name}`} className="field">{f.label || f.name}
          <input type={f.type === "date" ? "date" : "text"} inputMode={f.type === "number" ? "decimal" : undefined} value={values[f.name] ?? ""}
            onChange={(e) => onChange(f.name, e.target.value)} placeholder={f.type === "number" ? "número" : f.type === "date" ? "" : "todos"} />
        </label>
      ))}
      {active.length > 0 && (
        <button className="btn ghost sm" onClick={() => active.forEach((f) => onChange(f.name, ""))}>Limpar filtros ({active.length})</button>
      )}
    </div>
  );
}

const TYPE_LABEL: Record<DashFilter["type"], string> = { text: "Texto", number: "Número", date: "Data" };

/** Definição dos filtros (modo edição). Lista com problemas (nome vazio/repetido) não é salva até corrigir. */
export function FiltersEditor({ filters, onChange }: { filters: DashFilter[]; onChange: (f: DashFilter[]) => void }) {
  const problems = filterProblems(filters);
  const set = (i: number, patch: Partial<DashFilter>) => onChange(filters.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const add = () => {
    let n = filters.length + 1;
    while (filters.some((f) => f.name === `filtro${n}`)) n++;
    onChange([...filters, { name: `filtro${n}`, label: "", type: "text", default: "" }]);
  };
  return (
    <details className="filters-editor no-print" open={filters.length > 0}>
      <summary>Filtros do dashboard ({filters.length})</summary>
      <p className="muted small" style={{ margin: "6px 0 10px" }}>
        Use <code>{"{{nome}}"}</code> no SQL dos tiles. Filtro vazio vale <code>NULL</code>: escreva, por exemplo, <code>{'WHERE ({{grupo}} IS NULL OR "group" = {{grupo}})'}</code>.
        Renomear um filtro não altera os SQLs que já o usam.
      </p>
      {filters.map((f, i) => (
        <div key={i} className="filter-row">
          <label className="field">Nome (no SQL)
            <input type="text" value={f.name} maxLength={40} onChange={(e) => set(i, { name: sanitizeName(e.target.value) })} aria-label={`Nome do filtro ${i + 1}`} />
          </label>
          <label className="field">Rótulo
            <input type="text" value={f.label} maxLength={80} onChange={(e) => set(i, { label: e.target.value })} aria-label={`Rótulo do filtro ${i + 1}`} />
          </label>
          <label className="field">Tipo
            <select value={f.type} onChange={(e) => set(i, { type: e.target.value as DashFilter["type"] })} aria-label={`Tipo do filtro ${i + 1}`}>
              {Object.entries(TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="field">Valor inicial
            <input type="text" value={f.default} maxLength={200} onChange={(e) => set(i, { default: e.target.value })} aria-label={`Valor inicial do filtro ${i + 1}`} />
          </label>
          <button className="btn ghost sm" onClick={() => onChange(filters.filter((_, j) => j !== i))} aria-label={`Remover filtro ${f.name || i + 1}`} title="Remover filtro">✕</button>
        </div>
      ))}
      {problems.length > 0 && <div className="alert small" role="alert">{problems.join(" ")} Corrija para salvar.</div>}
      <button className="btn sm" onClick={add} disabled={filters.length >= 10}>+ Filtro</button>
    </details>
  );
}
