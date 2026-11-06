import { useState, type ReactNode } from "react";
import {
  CAST_LABEL, DATE_PART_LABEL, FN_LABEL, MATH_LABEL, MULTI_VALUE, NO_VALUE, OPERATOR_LABEL, TEXT_FN_LABEL, dateColumns, numericColumns,
  parseNumberList, parseTextList, type ColumnInfo, type Condition, type Operand, type Operator, type Step,
} from "../../lib/transforms";

interface Props { step: Step; cols: ColumnInfo[]; onChange: (s: Step) => void }
type Of<T extends Step["op"]> = Extract<Step, { op: T }>;

const Field = ({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) => (
  <label className="field">{label}{children}{hint && <span className="muted small">{hint}</span>}</label>
);

function ColumnSelect({ cols, value, onChange, label, only }: { cols: ColumnInfo[]; value: string; onChange: (v: string) => void; label: string; only?: ColumnInfo[] }) {
  const list = only ?? cols;
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {list.length === 0 && <option value="">(nenhuma coluna disponível)</option>}
        {list.map((c) => <option key={c.name} value={c.name}>{c.name} · {c.dtype}</option>)}
      </select>
    </Field>
  );
}

function ColumnPicker({ cols, selected, onChange, label, hint }: { cols: ColumnInfo[]; selected: string[]; onChange: (v: string[]) => void; label: string; hint?: string }) {
  const toggle = (n: string) => onChange(selected.includes(n) ? selected.filter((x) => x !== n) : [...selected, n]);
  return (
    <fieldset className="access-people" aria-label={label}>
      <legend className="small muted">{label}{hint ? ` — ${hint}` : ""}</legend>
      {cols.length === 0 && <span className="muted small">Nenhuma coluna deste tipo.</span>}
      {cols.map((c) => <label key={c.name} className="check"><input type="checkbox" checked={selected.includes(c.name)} onChange={() => toggle(c.name)} /> {c.name} <span className="muted small">{c.dtype}</span></label>)}
    </fieldset>
  );
}

const OperandInput = ({ label, value, cols, onChange, numeric = false }: { label: string; value: Operand; cols: ColumnInfo[]; onChange: (o: Operand) => void; numeric?: boolean }) => {
  const kind = "col" in value ? "col" : "num" in value ? "num" : "text" in value ? "text" : "null";
  const pick = (k: string) => onChange(k === "col" ? { col: (numeric ? numericColumns(cols) : cols)[0]?.name ?? "" } : k === "num" ? { num: 0 } : k === "text" ? { text: "" } : { null: true });
  return (
    <div className="operand">
      <span className="small muted">{label}</span>
      <div className="operand-row">
        <select value={kind} onChange={(e) => pick(e.target.value)} aria-label={`Tipo de ${label}`}>
          <option value="col">Coluna</option><option value="num">Número</option>
          {!numeric && <><option value="text">Texto</option><option value="null">Vazio</option></>}
        </select>
        {"col" in value && <select value={value.col} onChange={(e) => onChange({ col: e.target.value })} aria-label={label}>{(numeric ? numericColumns(cols) : cols).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select>}
        {"num" in value && <input type="number" step="any" value={Number.isFinite(value.num) ? value.num : ""} onChange={(e) => onChange({ num: e.target.value === "" ? NaN : Number(e.target.value) })} aria-label={label} />}
        {"text" in value && <input value={value.text} onChange={(e) => onChange({ text: e.target.value })} aria-label={label} />}
      </div>
    </div>
  );
};

function Conditions({ conditions, combine, cols, onChange }: { conditions: Condition[]; combine: "and" | "or"; cols: ColumnInfo[]; onChange: (c: Condition[], combine: "and" | "or") => void }) {
  const set = (i: number, patch: Partial<Condition>) => onChange(conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)), combine);
  return (
    <div className="conditions">
      {conditions.map((c, i) => (
        <div key={i} className="condition-row">
          <select value={c.column} onChange={(e) => set(i, { column: e.target.value })} aria-label={`Coluna da condição ${i + 1}`}>
            {cols.map((x) => <option key={x.name} value={x.name}>{x.name}</option>)}
          </select>
          <select value={c.operator} onChange={(e) => set(i, { operator: e.target.value as Operator })} aria-label={`Operador da condição ${i + 1}`}>
            {(Object.keys(OPERATOR_LABEL) as Operator[]).map((o) => <option key={o} value={o}>{OPERATOR_LABEL[o]}</option>)}
          </select>
          {MULTI_VALUE.includes(c.operator)
            ? <input placeholder="valores separados por vírgula" value={(c.values ?? []).join(", ")} onChange={(e) => set(i, { values: parseTextList(e.target.value) })} aria-label={`Valores da condição ${i + 1}`} />
            : !NO_VALUE.includes(c.operator) && <input placeholder="valor" value={c.value ?? ""} onChange={(e) => set(i, { value: e.target.value })} aria-label={`Valor da condição ${i + 1}`} />}
          {conditions.length > 1 && <button type="button" className="btn ghost sm" onClick={() => onChange(conditions.filter((_, j) => j !== i), combine)} aria-label={`Remover condição ${i + 1}`}>✕</button>}
        </div>
      ))}
      <div className="condition-actions">
        <button type="button" className="btn ghost sm" onClick={() => onChange([...conditions, { column: cols[0]?.name ?? "", operator: "eq", value: "" }], combine)}>+ condição</button>
        {conditions.length > 1 && (
          <label className="small">Combinar com{" "}
            <select value={combine} onChange={(e) => onChange(conditions, e.target.value as "and" | "or")} aria-label="Combinar condições">
              <option value="and">E (todas)</option><option value="or">OU (qualquer uma)</option>
            </select>
          </label>
        )}
      </div>
    </div>
  );
}

export function StepForm({ step, cols, onChange }: Props) {
  const nameField = (s: Step & { name: string }) => <Field label="Nome da nova coluna"><input value={s.name} onChange={(e) => onChange({ ...s, name: e.target.value } as Step)} maxLength={100} aria-label="Nome da nova coluna" /></Field>;
  const num = numericColumns(cols);
  switch (step.op) {
    case "select": {
      const s = step as Of<"select">;
      return (
        <>
          <Field label="O que fazer"><select value={s.mode} onChange={(e) => onChange({ ...s, mode: e.target.value as "keep" | "drop" })} aria-label="O que fazer"><option value="keep">Manter só as colunas marcadas (na ordem em que marcar)</option><option value="drop">Remover as colunas marcadas</option></select></Field>
          <ColumnPicker cols={cols} selected={s.columns} onChange={(columns) => onChange({ ...s, columns })} label="Colunas" />
        </>
      );
    }
    case "rename": {
      const s = step as Of<"rename">;
      return (
        <div className="rename-grid">
          {cols.map((c) => (
            <label key={c.name} className="field">{c.name}
              <input placeholder="novo nome" value={s.mapping[c.name] ?? ""} aria-label={`Novo nome de ${c.name}`}
                onChange={(e) => { const m = { ...s.mapping }; if (e.target.value === "") delete m[c.name]; else m[c.name] = e.target.value; onChange({ ...s, mapping: m }); }} />
            </label>
          ))}
        </div>
      );
    }
    case "cast": {
      const s = step as Of<"cast">;
      return (
        <>
          <ColumnSelect cols={cols} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna" />
          <Field label="Novo tipo" hint="Valores que não puderem ser convertidos viram vazios.">
            <select value={s.to} onChange={(e) => onChange({ ...s, to: e.target.value as Of<"cast">["to"] })} aria-label="Novo tipo">{Object.entries(CAST_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          </Field>
        </>
      );
    }
    case "filter": {
      const s = step as Of<"filter">;
      return <Conditions conditions={s.conditions} combine={s.combine} cols={cols} onChange={(conditions, combine) => onChange({ ...s, conditions, combine })} />;
    }
    case "sort": {
      const s = step as Of<"sort">;
      const set = (i: number, patch: Partial<Of<"sort">["keys"][number]>) => onChange({ ...s, keys: s.keys.map((k, j) => (j === i ? { ...k, ...patch } : k)) });
      return (
        <>
          {s.keys.map((k, i) => (
            <div key={i} className="condition-row">
              <select value={k.column} onChange={(e) => set(i, { column: e.target.value })} aria-label={`Coluna da ordenação ${i + 1}`}>{cols.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select>
              <select value={k.desc ? "desc" : "asc"} onChange={(e) => set(i, { desc: e.target.value === "desc" })} aria-label={`Sentido da ordenação ${i + 1}`}><option value="asc">crescente</option><option value="desc">decrescente</option></select>
              {s.keys.length > 1 && <button type="button" className="btn ghost sm" onClick={() => onChange({ ...s, keys: s.keys.filter((_, j) => j !== i) })} aria-label={`Remover ordenação ${i + 1}`}>✕</button>}
            </div>
          ))}
          <div><button type="button" className="btn ghost sm" onClick={() => onChange({ ...s, keys: [...s.keys, { column: cols[0]?.name ?? "", desc: false }] })}>+ critério</button></div>
          <p className="muted small" style={{ margin: 0 }}>Valores vazios ficam por último.</p>
        </>
      );
    }
    case "dedupe": {
      const s = step as Of<"dedupe">;
      return <ColumnPicker cols={cols} selected={s.columns} onChange={(columns) => onChange({ ...s, columns })} label="Considerar iguais as linhas que repetem" hint="nenhuma marcada = linha inteira; fica a primeira" />;
    }
    case "drop_nulls": {
      const s = step as Of<"drop_nulls">;
      return <ColumnPicker cols={cols} selected={s.columns} onChange={(columns) => onChange({ ...s, columns })} label="Remover a linha se estiver vazia em" hint="nenhuma marcada = qualquer coluna" />;
    }
    case "fill_nulls": {
      const s = step as Of<"fill_nulls">;
      return (
        <>
          <ColumnSelect cols={cols} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna" />
          <Field label="Preencher com">
            <select value={s.how} onChange={(e) => onChange({ ...s, how: e.target.value as Of<"fill_nulls">["how"] })} aria-label="Preencher com"><option value="value">Um valor fixo</option><option value="mean">A média da coluna</option><option value="median">A mediana da coluna</option></select>
          </Field>
          {s.how === "value" && <Field label="Valor"><input value={s.value ?? ""} onChange={(e) => onChange({ ...s, value: e.target.value })} aria-label="Valor de preenchimento" /></Field>}
          {s.how !== "value" && <div className="alert" role="note">Preencher com {s.how === "mean" ? "a média" : "a mediana"} <strong>reduz a variância</strong> e pode distorcer testes e intervalos de confiança. Prefira remover as linhas ou usar análises que aceitem dados ausentes.</div>}
        </>
      );
    }
    case "row_stat": {
      const s = step as Of<"row_stat">;
      return (
        <>
          {nameField(s)}
          <Field label="Calcular"><select value={s.fn} onChange={(e) => onChange({ ...s, fn: e.target.value as Of<"row_stat">["fn"] })} aria-label="Calcular">{Object.entries(FN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <ColumnPicker cols={num} selected={s.columns} onChange={(columns) => onChange({ ...s, columns })} label="Colunas numéricas" hint="uma linha por vez, entre as colunas" />
          <label className="check"><input type="checkbox" checked={s.require_all} onChange={(e) => onChange({ ...s, require_all: e.target.checked })} /><span>Só calcular quando todas as colunas da linha estiverem preenchidas<br /><span className="muted small">Sem isto, valores vazios são ignorados (a média de 4 e vazio é 4).</span></span></label>
        </>
      );
    }
    case "arith": {
      const s = step as Of<"arith">;
      return (
        <>
          {nameField(s)}
          <OperandInput label="Lado esquerdo" value={s.left} cols={cols} numeric onChange={(left) => onChange({ ...s, left })} />
          <Field label="Operação"><select value={s.operator} onChange={(e) => onChange({ ...s, operator: e.target.value as Of<"arith">["operator"] })} aria-label="Operação"><option value="+">+ somar</option><option value="-">− subtrair</option><option value="*">× multiplicar</option><option value="/">÷ dividir (÷ 0 vira vazio)</option></select></Field>
          <OperandInput label="Lado direito" value={s.right} cols={cols} numeric onChange={(right) => onChange({ ...s, right })} />
        </>
      );
    }
    case "math": {
      const s = step as Of<"math">;
      return (
        <>
          {nameField(s)}
          <Field label="Função"><select value={s.fn} onChange={(e) => onChange({ ...s, fn: e.target.value as Of<"math">["fn"] })} aria-label="Função">{Object.entries(MATH_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <ColumnSelect cols={cols} only={num} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna" />
          {s.fn === "round" && <Field label="Casas decimais"><input type="number" min={0} max={15} value={s.digits} onChange={(e) => onChange({ ...s, digits: Math.max(0, Math.min(15, Number(e.target.value) || 0)) })} aria-label="Casas decimais" /></Field>}
          {["sqrt", "ln", "log10"].includes(s.fn) && <p className="muted small" style={{ margin: 0 }}>Valores fora do domínio (raiz de negativo, log de zero ou negativo) viram vazios.</p>}
        </>
      );
    }
    case "cond": {
      const s = step as Of<"cond">;
      return (
        <>
          {nameField(s)}
          <span className="small muted">Se…</span>
          <Conditions conditions={s.conditions} combine={s.combine} cols={cols} onChange={(conditions, combine) => onChange({ ...s, conditions, combine })} />
          <OperandInput label="Então" value={s.then} cols={cols} onChange={(then) => onChange({ ...s, then })} />
          <OperandInput label="Senão" value={s.otherwise} cols={cols} onChange={(otherwise) => onChange({ ...s, otherwise })} />
          <p className="muted small" style={{ margin: 0 }}>“Então” e “senão” precisam ser do mesmo tipo. Linhas com valor vazio na condição caem no “senão”.</p>
        </>
      );
    }
    case "bins": return <BinsForm s={step as Of<"bins">} cols={cols} num={num} onChange={onChange} nameField={nameField} />;
    case "replace": {
      const s = step as Of<"replace">;
      const pairs = Object.entries(s.mapping);
      const setPairs = (next: [string, string][]) => onChange({ ...s, mapping: Object.fromEntries(next) });
      return (
        <>
          <ColumnSelect cols={cols} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna" />
          <Field label="Nome da nova coluna" hint="Em branco: substitui na própria coluna."><input value={s.name ?? ""} onChange={(e) => onChange({ ...s, name: e.target.value })} aria-label="Nome da nova coluna" /></Field>
          {pairs.map(([from, to], i) => (
            <div key={i} className="condition-row">
              <input placeholder="valor atual" value={from} onChange={(e) => setPairs(pairs.map((p, j) => (j === i ? [e.target.value, p[1]] : p)))} aria-label={`Valor atual ${i + 1}`} />
              <span>→</span>
              <input placeholder="novo valor" value={to} onChange={(e) => setPairs(pairs.map((p, j) => (j === i ? [p[0], e.target.value] : p)))} aria-label={`Novo valor ${i + 1}`} />
              {pairs.length > 1 && <button type="button" className="btn ghost sm" onClick={() => setPairs(pairs.filter((_, j) => j !== i))} aria-label={`Remover substituição ${i + 1}`}>✕</button>}
            </div>
          ))}
          <div><button type="button" className="btn ghost sm" onClick={() => onChange({ ...s, mapping: { ...s.mapping, [freshKey(s.mapping)]: "" } })}>+ substituição</button></div>
          <p className="muted small" style={{ margin: 0 }}>O resultado é texto; valores sem regra ficam como estão.</p>
        </>
      );
    }
    case "text_fn": {
      const s = step as Of<"text_fn">;
      return (
        <>
          {nameField(s)}
          <Field label="Operação"><select value={s.fn} onChange={(e) => onChange({ ...s, fn: e.target.value as Of<"text_fn">["fn"] })} aria-label="Operação">{Object.entries(TEXT_FN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <ColumnSelect cols={cols} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna" />
        </>
      );
    }
    case "concat": {
      const s = step as Of<"concat">;
      return (
        <>
          {nameField(s)}
          <ColumnPicker cols={cols} selected={s.columns} onChange={(columns) => onChange({ ...s, columns })} label="Colunas (na ordem marcada)" />
          <Field label="Separador"><input value={s.sep} maxLength={20} onChange={(e) => onChange({ ...s, sep: e.target.value })} aria-label="Separador" /></Field>
        </>
      );
    }
    case "date_part": {
      const s = step as Of<"date_part">;
      return (
        <>
          {nameField(s)}
          <ColumnSelect cols={cols} only={dateColumns(cols)} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna de data" />
          <Field label="Parte"><select value={s.part} onChange={(e) => onChange({ ...s, part: e.target.value as Of<"date_part">["part"] })} aria-label="Parte">{Object.entries(DATE_PART_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          {dateColumns(cols).length === 0 && <p className="muted small" style={{ margin: 0 }}>Nenhuma coluna de data. Use “Mudar o tipo de uma coluna” → data primeiro.</p>}
        </>
      );
    }
    case "formula": {
      const s = step as Of<"formula">;
      return (
        <>
          {nameField(s)}
          <Field label="Fórmula" hint="Use os nomes das colunas; aspas duplas para nomes com espaço.">
            <textarea rows={3} value={s.expr} onChange={(e) => onChange({ ...s, expr: e.target.value })} aria-label="Fórmula" placeholder='ex.: round((nota1 + nota2) / 2, 1)' />
          </Field>
          <p className="muted small" style={{ margin: 0 }}>
            Permitido: + − * / %, comparações, AND/OR/NOT, CASE WHEN, COALESCE, NULLIF, GREATEST, LEAST, ABS, ROUND, FLOOR, CEIL, SQRT, LN, LOG, EXP, POWER,
            UPPER, LOWER, TRIM, LENGTH, SUBSTRING, CONCAT, YEAR, MONTH, DAY, QUARTER e CAST para número, texto ou data. Funções de agregação e subconsultas não.
          </p>
        </>
      );
    }
  }
}

const freshKey = (m: Record<string, string>): string => { let i = m[""] === undefined ? 0 : 1; while (m[" ".repeat(i)] !== undefined) i++; return " ".repeat(i); };

function BinsForm({ s, cols, num, onChange, nameField }: { s: Of<"bins">; cols: ColumnInfo[]; num: ColumnInfo[]; onChange: (s: Step) => void; nameField: (s: Of<"bins">) => ReactNode }) {
  // o texto fica em estado local: "5," não pode virar [5] no meio da digitação
  const [edges, setEdges] = useState(s.edges.join(", "));
  const [labels, setLabels] = useState(s.labels.join(", "));
  return (
    <>
      {nameField(s)}
      <ColumnSelect cols={cols} only={num} value={s.column} onChange={(column) => onChange({ ...s, column })} label="Coluna numérica" />
      <Field label="Limites das faixas" hint="Separados por vírgula, em ordem crescente. Cada faixa inclui o limite inferior: 5, 8 → menor que 5 | 5 a menos de 8 | 8 ou mais.">
        <input value={edges} placeholder="ex.: 5, 8" aria-label="Limites das faixas" onChange={(e) => { setEdges(e.target.value); const n = parseNumberList(e.target.value); if (n) onChange({ ...s, edges: n }); }} />
      </Field>
      <Field label="Rótulos (opcional)" hint={`Informe ${s.edges.length + 1} rótulos na ordem, ou deixe em branco para rótulos automáticos.`}>
        <input value={labels} placeholder="ex.: baixa, média, alta" aria-label="Rótulos das faixas" onChange={(e) => { setLabels(e.target.value); onChange({ ...s, labels: parseTextList(e.target.value) }); }} />
      </Field>
      {edges.trim() !== "" && parseNumberList(edges) === null && <div className="alert" role="alert">Os limites devem ser números separados por vírgula.</div>}
    </>
  );
}
