import { describe, expect, it } from "vitest";
import { cleanStep, defaultStep, describeStep, failingStep, freeName, moveStep, parseNumberList, parseTextList, stepProblem, STEP_KINDS, type ColumnInfo, type Step } from "./transforms";

const cols: ColumnInfo[] = [{ name: "id", dtype: "INTEGER" }, { name: "grupo", dtype: "VARCHAR" }, { name: "nota1", dtype: "DOUBLE" }, { name: "nota2", dtype: "DECIMAL(5,2)" }, { name: "data", dtype: "DATE" }];

describe("defaultStep", () => {
  it("existe um valor inicial para cada tipo de passo do catálogo", () => {
    for (const k of STEP_KINDS) expect(defaultStep(k.op, cols).op).toBe(k.op);
  });
  it("sugere colunas certas: numéricas para estatísticas e data para parte de data", () => {
    const row = defaultStep("row_stat", cols) as Extract<Step, { op: "row_stat" }>;
    expect(row.columns).toEqual(["id", "nota1"]);
    expect((defaultStep("date_part", cols) as Extract<Step, { op: "date_part" }>).column).toBe("data");
  });
  it("nunca sugere um nome que já exista", () => {
    expect(freeName("nota1", cols)).toBe("nota1_2");
    expect(freeName("media", cols)).toBe("media");
    expect(freeName("NOTA1", cols)).toBe("NOTA1_2");
  });
});

describe("describeStep", () => {
  it("descreve em português, legível numa lista", () => {
    expect(describeStep({ op: "row_stat", name: "media", fn: "mean", columns: ["a", "b", "c"], require_all: false })).toBe('"media" = média de a, b, c');
    expect(describeStep({ op: "filter", combine: "and", conditions: [{ column: "grupo", operator: "eq", value: "A" }, { column: "nota1", operator: "is_null" }] })).toBe("Filtrar: grupo é igual a A e nota1 está vazio");
    expect(describeStep({ op: "select", mode: "keep", columns: ["a", "b", "c", "d", "e", "f"] })).toBe("Manter colunas: a, b, c, d e mais 2");
    expect(describeStep({ op: "cond", name: "s", combine: "and", conditions: [{ column: "n", operator: "ge", value: "6" }], then: { text: "ok" }, otherwise: { null: true } })).toBe('"s" = se n maior ou igual a 6 então "ok" senão vazio');
  });
  it("descreve todos os tipos sem estourar", () => {
    for (const k of STEP_KINDS) expect(describeStep(defaultStep(k.op, cols)).length).toBeGreaterThan(3);
  });
});

describe("stepProblem", () => {
  it("passo recém-criado de nova coluna pede o que falta", () => {
    expect(stepProblem({ op: "select", columns: [], mode: "keep" }, cols)).toMatch(/ao menos uma coluna/);
    expect(stepProblem({ ...(defaultStep("row_stat", cols) as Extract<Step, { op: "row_stat" }>), columns: ["nota1"] }, cols)).toMatch(/2 colunas/);
    expect(stepProblem(defaultStep("filter", cols), cols)).toMatch(/valor da condição/);
    expect(stepProblem(defaultStep("formula", cols), cols)).toMatch(/fórmula/);
  });
  it("recusa nome repetido (sem diferenciar maiúsculas) mas aceita o próprio nome ao editar", () => {
    const s = { ...(defaultStep("text_fn", cols) as Extract<Step, { op: "text_fn" }>), name: "NOTA1" };
    expect(stepProblem(s, cols)).toMatch(/já existe/);
    expect(stepProblem(s, cols, s)).toBeNull();
  });
  it("faixas: limites crescentes e rótulos na quantidade certa", () => {
    const b = defaultStep("bins", cols) as Extract<Step, { op: "bins" }>;
    expect(stepProblem(b, cols)).toMatch(/ao menos um limite/);
    expect(stepProblem({ ...b, edges: [5, 3] }, cols)).toMatch(/crescentes/);
    expect(stepProblem({ ...b, edges: [5, 8], labels: ["a", "b"] }, cols)).toMatch(/3 rótulos/);
    expect(stepProblem({ ...b, edges: [5, 8] }, cols)).toBeNull();
  });
  it("substituir na própria coluna não conta como nome repetido", () => {
    expect(stepProblem({ op: "replace", column: "grupo", name: "grupo", mapping: { A: "x" } }, cols)).toBeNull();
  });
});

describe("listas digitadas", () => {
  it("números com vírgula decimal ou separador", () => {
    expect(parseNumberList("5, 8, 10")).toEqual([5, 8, 10]);
    expect(parseNumberList("5; 8,5; 10")).toEqual([5, 8.5, 10]);
    expect(parseNumberList("")).toEqual([]);
    expect(parseNumberList("5, abc")).toBeNull();
  });
  it("textos", () => expect(parseTextList("baixa, média ; alta")).toEqual(["baixa", "média", "alta"]));
});

describe("cleanStep", () => {
  it("tira a entrada vazia da substituição e o valor que não se aplica ao operador", () => {
    expect(cleanStep({ op: "replace", column: "g", name: " ", mapping: { "": "", A: "x" } })).toEqual({ op: "replace", column: "g", name: undefined, mapping: { A: "x" } });
    const f = cleanStep({ op: "filter", combine: "and", conditions: [{ column: "n", operator: "is_null", value: "x" }, { column: "g", operator: "in", value: "z", values: ["A"] }, { column: "g", operator: "eq", value: "A", values: [] }] }) as Extract<Step, { op: "filter" }>;
    expect(f.conditions[0]).toEqual({ column: "n", operator: "is_null" });
    expect(f.conditions[1].value).toBeUndefined();
    expect(f.conditions[2].values).toBeUndefined();
  });
  it("apara espaços do nome da coluna nova", () => expect((cleanStep({ op: "formula", name: "  x ", expr: "1" }) as { name: string }).name).toBe("x"));
});

describe("erros e ordem", () => {
  it("acha o passo apontado pelo servidor", () => {
    expect(failingStep("Passo 3 (sort): coluna não encontrada")).toBe(3);
    expect(failingStep("outro erro")).toBeNull();
    expect(failingStep(null)).toBeNull();
  });
  it("move passos sem sair dos limites", () => {
    expect(moveStep([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(moveStep([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
    expect(moveStep([1, 2, 3], 2, 1)).toEqual([1, 2, 3]);
  });
});
