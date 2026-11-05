import { useEffect, useMemo, useState } from "react";
import type { Column, Dataset } from "../api";
import { candidates, problems, resolveState, type AnalysisDef, type FormState, type Item, type NumberItem, type VarSlot } from "../lib/analyses";

const levelsLabel = (n: number) => `${n} ${n === 1 ? "nível" : "níveis"}`;
const colLabel = (c: Column) => (c.measurement !== "scale" && c.n_distinct !== null ? `${c.name} (${levelsLabel(c.n_distinct)})` : c.name);

function SlotField({ slot, dataset, chosen, onPick }: { slot: VarSlot; dataset: Dataset; chosen: string[]; onPick: (names: string[]) => void }) {
  const cands = candidates(slot, dataset);
  if (!slot.multi) {
    return (
      <label className="field">{slot.label}
        <select value={chosen[0] ?? ""} onChange={(e) => onPick(e.target.value ? [e.target.value] : [])} disabled={cands.length === 0}>
          {chosen.length === 0 && <option value="">{slot.required ? "Escolha…" : "—"}</option>}
          {cands.map((c) => <option key={c.name} value={c.name}>{colLabel(c)}</option>)}
        </select>
      </label>
    );
  }
  return (
    <fieldset>
      <legend>{slot.label}</legend>
      {cands.length === 0 && <span className="muted small">Nenhuma coluna {slot.levels.map((l) => (l === "scale" ? "escalar" : l)).join(" ou ")} disponível.</span>}
      <div className="check-list">
        {cands.map((c) => (
          <label key={c.name} className="check">
            <input type="checkbox" checked={chosen.includes(c.name)} onChange={(e) => onPick(e.target.checked ? [...chosen, c.name] : chosen.filter((n) => n !== c.name))} />
            {colLabel(c)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Campo numérico com texto local: digitar "0." não pode ser reformatado para "0" no meio da digitação. */
function NumberField({ item, value, onCommit }: { item: NumberItem; value: number; onCommit: (n: number) => void }) {
  const [text, setText] = useState(String(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => { if (!focused) setText(String(value)); }, [value, focused]);
  const parse = (raw: string) => (raw.trim() === "" ? NaN : Number(raw.replace(",", ".")));
  return (
    <label className="field">{item.label}
      <input type="number" inputMode="decimal" min={item.min} max={item.max} step={item.step} value={text}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); const n = parse(text); if (!Number.isFinite(n) || n < item.min || n > item.max) setText(String(value)); }}
        onChange={(e) => { setText(e.target.value); const n = parse(e.target.value); if (Number.isFinite(n) && n >= item.min && n <= item.max) onCommit(n); }} />
    </label>
  );
}

function ItemField({ item, value, onChange }: { item: Item; value: boolean | number | string; onChange: (v: boolean | number | string) => void }) {
  if (item.type === "toggle") {
    return <label className="check"><input type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />{item.label}</label>;
  }
  if (item.type === "number") return <NumberField item={item} value={Number(value)} onCommit={onChange} />;
  return (
    <label className="field">{item.label}
      <select value={String(value)} onChange={(e) => onChange(e.target.value)}>{item.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
    </label>
  );
}

interface Props {
  def: AnalysisDef;
  dataset: Dataset;
  state: FormState;
  onChange: (s: FormState) => void;
}

/**
 * Formulário de uma análise, gerado da sua definição. Controlado: quem usa decide onde guardar o estado (aba ou bloco).
 * Mostra sempre o estado EFETIVO (padrões preenchidos, colunas inválidas descartadas) e o grava de volta, para que o que
 * está na tela seja exatamente o que será salvo/executado.
 */
export function AnalysisForm({ def, dataset, state, onChange }: Props) {
  const resolved = useMemo(() => resolveState(def, dataset, state), [def, dataset, state]);
  useEffect(() => {
    if (JSON.stringify(resolved) !== JSON.stringify(state)) onChange(resolved);
  }, [resolved, state, onChange]);
  const issues = problems(def, dataset, resolved);

  const setVar = (key: string, names: string[]) => onChange({ ...resolved, vars: { ...resolved.vars, [key]: names } });
  const setValue = (key: string, v: boolean | number | string) => onChange({ ...resolved, values: { ...resolved.values, [key]: v } });

  return (
    <>
      {def.slots.map((slot) => <SlotField key={slot.key} slot={slot} dataset={dataset} chosen={resolved.vars[slot.key]} onPick={(n) => setVar(slot.key, n)} />)}
      {issues.map((msg) => <div key={msg} className="alert info small" role="status">{msg}</div>)}
      {def.sections.map((section) => {
        const items = section.items.filter((i) => !i.showIf || i.showIf(resolved.values));
        return items.length === 0 ? null : (
          <fieldset key={section.title}>
            <legend>{section.title}</legend>
            {items.map((i) => <ItemField key={i.key} item={i} value={resolved.values[i.key]} onChange={(v) => setValue(i.key, v)} />)}
          </fieldset>
        );
      })}
    </>
  );
}
