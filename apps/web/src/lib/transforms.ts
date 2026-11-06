/** Passos de transformação (a "receita"): espelha o modelo do servidor, com rótulos, valores iniciais e validação local. */
export type Operator = "eq" | "ne" | "gt" | "ge" | "lt" | "le" | "contains" | "not_contains" | "starts_with" | "ends_with" | "is_null" | "not_null" | "in" | "not_in";
export interface Condition { column: string; operator: Operator; value?: string; values?: string[] }
export type Operand = { col: string } | { num: number } | { text: string } | { null: true };
export interface ColumnInfo { name: string; dtype: string }

export type Step =
  | { op: "select"; columns: string[]; mode: "keep" | "drop" }
  | { op: "rename"; mapping: Record<string, string> }
  | { op: "cast"; column: string; to: "number" | "integer" | "text" | "date" | "boolean" }
  | { op: "filter"; conditions: Condition[]; combine: "and" | "or" }
  | { op: "sort"; keys: { column: string; desc: boolean }[] }
  | { op: "dedupe"; columns: string[] }
  | { op: "drop_nulls"; columns: string[] }
  | { op: "fill_nulls"; column: string; how: "value" | "mean" | "median"; value?: string }
  | { op: "row_stat"; name: string; fn: "mean" | "sum" | "min" | "max" | "count"; columns: string[]; require_all: boolean }
  | { op: "arith"; name: string; left: Operand; operator: "+" | "-" | "*" | "/"; right: Operand }
  | { op: "math"; name: string; fn: "round" | "abs" | "sqrt" | "ln" | "log10" | "exp" | "floor" | "ceil" | "square"; column: string; digits: number }
  | { op: "cond"; name: string; conditions: Condition[]; combine: "and" | "or"; then: Operand; otherwise: Operand }
  | { op: "bins"; name: string; column: string; edges: number[]; labels: string[] }
  | { op: "replace"; name?: string; column: string; mapping: Record<string, string> }
  | { op: "text_fn"; name: string; fn: "upper" | "lower" | "trim" | "length"; column: string }
  | { op: "concat"; name: string; columns: string[]; sep: string }
  | { op: "date_part"; name: string; column: string; part: "year" | "quarter" | "month" | "day" | "week" | "weekday" | "year_month" }
  | { op: "formula"; name: string; expr: string };

export type StepOp = Step["op"];
export interface Recipe { source_id: string; steps: Step[] }

export const OPERATOR_LABEL: Record<Operator, string> = {
  eq: "é igual a", ne: "é diferente de", gt: "maior que", ge: "maior ou igual a", lt: "menor que", le: "menor ou igual a",
  contains: "contém", not_contains: "não contém", starts_with: "começa com", ends_with: "termina com",
  is_null: "está vazio", not_null: "não está vazio", in: "é um de", not_in: "não é um de",
};
export const NO_VALUE: Operator[] = ["is_null", "not_null"];
export const MULTI_VALUE: Operator[] = ["in", "not_in"];

export const FN_LABEL = { mean: "média", sum: "soma", min: "mínimo", max: "máximo", count: "contagem (valores preenchidos)" } as const;
export const MATH_LABEL = { round: "arredondar", abs: "valor absoluto", sqrt: "raiz quadrada", ln: "logaritmo natural", log10: "logaritmo (base 10)", exp: "exponencial", floor: "arredondar para baixo", ceil: "arredondar para cima", square: "ao quadrado" } as const;
export const CAST_LABEL = { number: "número decimal", integer: "número inteiro", text: "texto", date: "data", boolean: "verdadeiro/falso" } as const;
export const DATE_PART_LABEL = { year: "ano", quarter: "trimestre", month: "mês", day: "dia", week: "semana do ano", weekday: "dia da semana (1 = segunda)", year_month: "ano-mês (AAAA-MM)" } as const;
export const TEXT_FN_LABEL = { upper: "MAIÚSCULAS", lower: "minúsculas", trim: "remover espaços das pontas", length: "comprimento" } as const;

export interface StepKind { op: StepOp; label: string; group: "Colunas" | "Linhas" | "Nova coluna" }
export const STEP_KINDS: StepKind[] = [
  { op: "select", label: "Escolher ou remover colunas", group: "Colunas" },
  { op: "rename", label: "Renomear colunas", group: "Colunas" },
  { op: "cast", label: "Mudar o tipo de uma coluna", group: "Colunas" },
  { op: "filter", label: "Filtrar linhas", group: "Linhas" },
  { op: "sort", label: "Ordenar", group: "Linhas" },
  { op: "dedupe", label: "Remover duplicatas", group: "Linhas" },
  { op: "drop_nulls", label: "Remover linhas com valores vazios", group: "Linhas" },
  { op: "fill_nulls", label: "Preencher valores vazios", group: "Linhas" },
  { op: "row_stat", label: "Média, soma, mín. ou máx. entre colunas", group: "Nova coluna" },
  { op: "arith", label: "Cálculo entre colunas e números (+ − × ÷)", group: "Nova coluna" },
  { op: "math", label: "Função matemática (arredondar, log, raiz…)", group: "Nova coluna" },
  { op: "cond", label: "Condicional (se… então… senão)", group: "Nova coluna" },
  { op: "bins", label: "Faixas (agrupar números em intervalos)", group: "Nova coluna" },
  { op: "replace", label: "Substituir valores", group: "Nova coluna" },
  { op: "text_fn", label: "Texto (maiúsculas, tamanho…)", group: "Nova coluna" },
  { op: "concat", label: "Juntar colunas de texto", group: "Nova coluna" },
  { op: "date_part", label: "Parte de uma data (ano, mês…)", group: "Nova coluna" },
  { op: "formula", label: "Fórmula livre", group: "Nova coluna" },
];

const isNum = (dtype: string) => /^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|DECIMAL)/i.test(dtype);
const isDate = (dtype: string) => /^(DATE|TIMESTAMP)/i.test(dtype);
export const numericColumns = (cols: ColumnInfo[]) => cols.filter((c) => isNum(c.dtype));
export const dateColumns = (cols: ColumnInfo[]) => cols.filter((c) => isDate(c.dtype));

/** Nome sugerido para a nova coluna que ainda não exista. */
export function freeName(base: string, cols: ColumnInfo[]): string {
  const taken = new Set(cols.map((c) => c.name.toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  for (let i = 2; ; i++) if (!taken.has(`${base}_${i}`.toLowerCase())) return `${base}_${i}`;
}

/** Passo recém-criado, já com valores razoáveis para as colunas disponíveis. */
export function defaultStep(op: StepOp, cols: ColumnInfo[]): Step {
  const first = cols[0]?.name ?? "";
  const num = numericColumns(cols);
  const firstNum = num[0]?.name ?? first;
  const date = dateColumns(cols)[0]?.name ?? first;
  switch (op) {
    case "select": return { op, columns: [], mode: "keep" };
    case "rename": return { op, mapping: {} };
    case "cast": return { op, column: first, to: "number" };
    case "filter": return { op, combine: "and", conditions: [{ column: first, operator: "eq", value: "" }] };
    case "sort": return { op, keys: [{ column: first, desc: false }] };
    case "dedupe": return { op, columns: [] };
    case "drop_nulls": return { op, columns: [] };
    case "fill_nulls": return { op, column: first, how: "value", value: "" };
    case "row_stat": return { op, name: freeName("media", cols), fn: "mean", columns: num.slice(0, 2).map((c) => c.name), require_all: false };
    case "arith": return { op, name: freeName("calculo", cols), left: { col: firstNum }, operator: "+", right: { num: 1 } };
    case "math": return { op, name: freeName("resultado", cols), fn: "round", column: firstNum, digits: 0 };
    case "cond": return { op, name: freeName("condicao", cols), combine: "and", conditions: [{ column: first, operator: "gt", value: "" }], then: { text: "sim" }, otherwise: { text: "não" } };
    case "bins": return { op, name: freeName("faixa", cols), column: firstNum, edges: [], labels: [] };
    case "replace": return { op, column: first, name: "", mapping: { "": "" } };
    case "text_fn": return { op, name: freeName("texto", cols), fn: "upper", column: first };
    case "concat": return { op, name: freeName("junto", cols), columns: [], sep: " " };
    case "date_part": return { op, name: freeName("ano", cols), column: date, part: "year" };
    case "formula": return { op, name: freeName("formula", cols), expr: "" };
  }
}

const list = (xs: string[], max = 4) => (xs.length <= max ? xs.join(", ") : `${xs.slice(0, max).join(", ")} e mais ${xs.length - max}`);
const operand = (o: Operand): string => ("col" in o ? o.col : "num" in o ? String(o.num) : "text" in o ? `"${o.text}"` : "vazio");
export const describeCondition = (c: Condition): string =>
  NO_VALUE.includes(c.operator) ? `${c.column} ${OPERATOR_LABEL[c.operator]}`
    : MULTI_VALUE.includes(c.operator) ? `${c.column} ${OPERATOR_LABEL[c.operator]} ${list(c.values ?? [])}`
      : `${c.column} ${OPERATOR_LABEL[c.operator]} ${c.value ?? ""}`;

export function describeStep(s: Step): string {
  switch (s.op) {
    case "select": return `${s.mode === "keep" ? "Manter" : "Remover"} colunas: ${list(s.columns)}`;
    case "rename": return `Renomear: ${list(Object.entries(s.mapping).map(([a, b]) => `${a} → ${b}`), 3)}`;
    case "cast": return `Tipo de ${s.column}: ${CAST_LABEL[s.to]}`;
    case "filter": return `Filtrar: ${s.conditions.map(describeCondition).join(s.combine === "and" ? " e " : " ou ")}`;
    case "sort": return `Ordenar por ${list(s.keys.map((k) => `${k.column}${k.desc ? " ↓" : " ↑"}`))}`;
    case "dedupe": return s.columns.length ? `Remover duplicatas por ${list(s.columns)}` : "Remover linhas duplicadas";
    case "drop_nulls": return s.columns.length ? `Remover linhas vazias em ${list(s.columns)}` : "Remover linhas com algum valor vazio";
    case "fill_nulls": return `Preencher vazios de ${s.column} com ${s.how === "value" ? `"${s.value ?? ""}"` : s.how === "mean" ? "a média" : "a mediana"}`;
    case "row_stat": return `"${s.name}" = ${FN_LABEL[s.fn].split(" ")[0]} de ${list(s.columns)}${s.require_all ? " (só linhas completas)" : ""}`;
    case "arith": return `"${s.name}" = ${operand(s.left)} ${s.operator} ${operand(s.right)}`;
    case "math": return `"${s.name}" = ${MATH_LABEL[s.fn]} de ${s.column}${s.fn === "round" ? ` (${s.digits} casas)` : ""}`;
    case "cond": return `"${s.name}" = se ${s.conditions.map(describeCondition).join(s.combine === "and" ? " e " : " ou ")} então ${operand(s.then)} senão ${operand(s.otherwise)}`;
    case "bins": return `"${s.name}" = faixas de ${s.column} (limites ${s.edges.join(", ")})`;
    case "replace": return `Substituir valores em ${s.column}${s.name && s.name !== s.column ? ` → "${s.name}"` : ""}`;
    case "text_fn": return `"${s.name}" = ${TEXT_FN_LABEL[s.fn]} de ${s.column}`;
    case "concat": return `"${s.name}" = ${list(s.columns)} juntas`;
    case "date_part": return `"${s.name}" = ${DATE_PART_LABEL[s.part].split(" (")[0]} de ${s.column}`;
    case "formula": return `"${s.name}" = ${s.expr}`;
  }
}

/** Texto digitado "5, 8, 10" -> [5, 8, 10]; null se algum item não for número. */
export function parseNumberList(text: string): number[] | null {
  const parts = text.split(/[;\n]|,(?!\d)/).map((p) => p.trim()).filter(Boolean);
  const nums = parts.map((p) => Number(p.replace(",", ".")));
  return nums.some((n) => !Number.isFinite(n)) ? null : nums;
}
export const parseTextList = (text: string): string[] => text.split(/[;,\n]/).map((p) => p.trim()).filter(Boolean);

const conditionProblem = (c: Condition): string | null => {
  if (!c.column) return "escolha a coluna da condição";
  if (NO_VALUE.includes(c.operator)) return null;
  if (MULTI_VALUE.includes(c.operator)) return (c.values ?? []).length ? null : "informe ao menos um valor";
  return (c.value ?? "").trim() === "" ? "informe o valor da condição" : null;
};
const operandProblem = (o: Operand, what: string): string | null => ("col" in o && !o.col ? `escolha a coluna de ${what}` : "num" in o && !Number.isFinite(o.num) ? `informe o número de ${what}` : null);

/** O que falta preencher antes de poder aplicar o passo (null = pronto). A validação de verdade é do servidor. */
export function stepProblem(s: Step, cols: ColumnInfo[], editing?: Step): string | null {
  const existing = new Set(cols.map((c) => c.name.toLowerCase()));
  if (editing && "name" in editing && editing.name) existing.delete(editing.name.toLowerCase());
  const newName = (name: string | undefined, inPlace = false): string | null =>
    !name?.trim() ? (inPlace ? null : "dê um nome à nova coluna") : existing.has(name.trim().toLowerCase()) && !inPlace ? `já existe uma coluna "${name.trim()}"` : null;
  switch (s.op) {
    case "select": return s.columns.length ? null : "escolha ao menos uma coluna";
    case "rename": return Object.keys(s.mapping).length ? null : "digite um novo nome para ao menos uma coluna";
    case "cast": case "sort": return null;
    case "filter": return s.conditions.map(conditionProblem).find(Boolean) ?? null;
    case "dedupe": case "drop_nulls": return null;
    case "fill_nulls": return s.how === "value" && (s.value ?? "") === "" ? "informe o valor de preenchimento" : null;
    case "row_stat": return newName(s.name) ?? (s.columns.length < 2 ? "escolha ao menos 2 colunas numéricas" : null);
    case "arith": return newName(s.name) ?? operandProblem(s.left, "o lado esquerdo") ?? operandProblem(s.right, "o lado direito");
    case "math": return newName(s.name) ?? (s.column ? null : "escolha a coluna");
    case "cond": return newName(s.name) ?? s.conditions.map(conditionProblem).find(Boolean) ?? operandProblem(s.then, "“então”") ?? operandProblem(s.otherwise, "“senão”");
    case "bins": return newName(s.name) ?? (s.edges.length === 0 ? "informe ao menos um limite (ex.: 5, 8)" : s.labels.length && s.labels.length !== s.edges.length + 1 ? `informe ${s.edges.length + 1} rótulos ou deixe em branco` : s.edges.some((e, i) => i > 0 && e <= s.edges[i - 1]) ? "os limites devem ser crescentes" : null);
    case "replace": return newName(s.name, true) ?? (Object.keys(s.mapping).filter((k) => k !== "").length ? null : "informe ao menos um valor a substituir");
    case "text_fn": return newName(s.name);
    case "concat": return newName(s.name) ?? (s.columns.length < 2 ? "escolha ao menos 2 colunas" : null);
    case "date_part": return newName(s.name) ?? (s.column ? null : "escolha a coluna de data");
    case "formula": return newName(s.name) ?? (s.expr.trim() ? null : "escreva a fórmula");
  }
}

/** Remove restos do formulário (entradas vazias) antes de enviar ao servidor. */
export function cleanStep(s: Step): Step {
  if (s.op === "replace") return { ...s, name: s.name?.trim() || undefined, mapping: Object.fromEntries(Object.entries(s.mapping).filter(([k]) => k !== "")) };
  if (s.op === "filter" || s.op === "cond") return { ...s, conditions: s.conditions.map((c) => (MULTI_VALUE.includes(c.operator) ? { ...c, value: undefined } : NO_VALUE.includes(c.operator) ? { column: c.column, operator: c.operator } : { ...c, values: undefined })) } as Step;
  if ("name" in s && typeof s.name === "string") return { ...s, name: s.name.trim() } as Step;
  return s;
}

/** Índice (1-based) do passo que o servidor apontou em "Passo 3 (sort): …", ou null. */
export const failingStep = (message: string | null): number | null => {
  const m = message ? /^Passo (\d+)\b/.exec(message) : null;
  return m ? Number(m[1]) : null;
};

export function moveStep<T>(steps: T[], i: number, dir: -1 | 1): T[] {
  const j = i + dir;
  if (j < 0 || j >= steps.length) return steps;
  const out = [...steps];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}
