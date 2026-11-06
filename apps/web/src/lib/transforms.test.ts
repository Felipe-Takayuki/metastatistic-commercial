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

describe("passos por grupo e janela", () => {
  it("descreve em português, com e sem grupo", () => {
    expect(describeStep({ op: "group_stat", name: "m", fn: "mean", column: "nota1", by: ["grupo"] })).toBe('"m" = média de nota1 por grupo');
    expect(describeStep({ op: "group_stat", name: "m", fn: "std", column: "nota1", by: [] })).toBe('"m" = desvio de nota1 (todas as linhas)');
    expect(describeStep({ op: "pct_total", name: "p", column: "v", by: ["a", "b"] })).toBe('"p" = % de v no total por a, b');
    expect(describeStep({ op: "rank", name: "r", column: "v", by: [], desc: false, method: "dense" })).toBe('"r" = posição de v (menor = 1) (todas as linhas)');
    expect(describeStep({ op: "running", name: "a", fn: "sum", column: "v", window: null, order_by: [{ column: "id", desc: false }], by: ["g"], require_full: false })).toBe('"a" = soma acumulada de v, ordem id ↑ por g');
    expect(describeStep({ op: "running", name: "mm", fn: "mean", column: "v", window: 3, order_by: [], by: [], require_full: true })).toBe('"mm" = média móvel de 3 linhas de v (todas as linhas)');
    expect(describeStep({ op: "lag", name: "d", column: "v", kind: "pct_change", periods: 2, order_by: [{ column: "id", desc: true }], by: [] })).toBe('"d" = variação % de v (2 linhas atrás), ordem id ↓ (todas as linhas)');
  });
  it("valida janela e período", () => {
    const run = defaultStep("running", cols) as Extract<Step, { op: "running" }>;
    expect(stepProblem(run, cols)).toBeNull();
    expect(stepProblem({ ...run, window: 1 }, cols)).toMatch(/ao menos 2 linhas/);
    const lag = defaultStep("lag", cols) as Extract<Step, { op: "lag" }>;
    expect(stepProblem({ ...lag, periods: 0 }, cols)).toMatch(/1 ou mais/);
    expect(stepProblem({ ...lag, name: "ID" }, cols)).toMatch(/já existe/);
  });
  it("janela vazia ou inválida vira acumulado; fração é arredondada para baixo", () => {
    const run = defaultStep("running", cols) as Extract<Step, { op: "running" }>;
    expect((cleanStep({ ...run, window: NaN }) as typeof run).window).toBeNull();
    expect((cleanStep({ ...run, window: 3.7 }) as typeof run).window).toBe(3);
    expect((cleanStep({ ...run, window: null }) as typeof run).window).toBeNull();
  });
  it("o catálogo agrupa os novos passos", () => expect(STEP_KINDS.filter((k) => k.group === "Por grupo e janela").map((k) => k.op)).toEqual(["group_stat", "pct_total", "rank", "zscore", "running", "lag"]));
});

describe("reformatar e combinar (8.4)", () => {
  type S<T extends Step["op"]> = Extract<Step, { op: T }>;
  it("o catálogo tem os cinco passos novos, em grupo próprio", () =>
    expect(STEP_KINDS.filter((k) => k.group === "Reformatar e combinar").map((k) => k.op)).toEqual(["summarize", "pivot", "unpivot", "join", "append"]));
  it("descreve cada um em português", () => {
    expect(describeStep({ op: "summarize", by: ["grupo"], aggs: [{ name: "n", fn: "count_rows" }, { name: "media", fn: "mean", column: "nota1" }] })).toBe("Resumir por grupo: n = número de linhas, media = média de nota1");
    expect(describeStep({ op: "summarize", by: [], aggs: [{ name: "n", fn: "count_rows" }] })).toBe("Resumir a tabela inteira: n = número de linhas");
    expect(describeStep({ op: "pivot", index: ["id"], names_from: "tempo", values: "nota", fn: "first", prefix: "" })).toBe("Pivotar: valores de tempo viram colunas (nota), identificando por id");
    expect(describeStep({ op: "unpivot", columns: ["a", "b"], names_to: "prova", values_to: "nota", drop_nulls: true })).toBe('Despivotar a, b em "prova" / "nota" (sem vazios)');
    const names = (id: string) => (id === "x" ? "nomes.csv" : id);
    expect(describeStep({ op: "join", other_id: "x", kind: "left", keys: [{ left: "id", right: "id" }, { left: "a", right: "b" }], columns: [], suffix: "_2", allow_multiple: false }, names)).toBe("Mesclar com nomes.csv por id, a = b (mantém as daqui)");
    expect(describeStep({ op: "append", other_id: "x", source_column: "lote", label_current: "1", label_other: "2" }, names)).toBe('Acrescentar linhas de nomes.csv (origem em "lote")');
  });
  it("resumir: nomes e colunas são exigidos, e o nome pode repetir a coluna original", () => {
    const s = defaultStep("summarize", cols) as S<"summarize">;
    expect(stepProblem(s, cols)).toBeNull();
    expect(stepProblem({ ...s, by: ["grupo"], aggs: [{ name: "grupo", fn: "count_rows" }] }, cols)).toMatch(/repetidos/);
    expect(stepProblem({ ...s, aggs: [{ name: " ", fn: "count_rows" }] }, cols)).toMatch(/nome a cada/);
    expect(stepProblem({ ...s, aggs: [{ name: "m", fn: "mean" }] }, cols)).toMatch(/escolha a coluna/);
    expect(stepProblem({ ...s, aggs: [{ name: "nota1", fn: "mean", column: "nota1" }] }, cols)).toBeNull(); // a original some, então o nome é livre
    expect(cleanStep({ ...s, aggs: [{ name: " n ", fn: "count_rows", column: "x" }] })).toEqual({ ...s, aggs: [{ name: "n", fn: "count_rows" }] });
  });
  it("pivotar e despivotar exigem colunas distintas", () => {
    const p = defaultStep("pivot", cols) as S<"pivot">;
    expect(stepProblem(p, cols)).toBeNull();
    expect(stepProblem({ ...p, names_from: p.index[0] }, cols)).toMatch(/diferentes/);
    expect(stepProblem({ ...p, index: [] }, cols)).toMatch(/identifique/);
    const u = defaultStep("unpivot", cols) as S<"unpivot">;
    expect(u.columns).toEqual(["id", "nota1"]);
    expect(stepProblem(u, cols)).toBeNull();
    expect(stepProblem({ ...u, columns: ["nota1"] }, cols)).toMatch(/ao menos 2/);
    expect(stepProblem({ ...u, names_to: "grupo" }, cols)).toMatch(/não podem repetir/); // 'grupo' continua existindo
    expect(stepProblem({ ...u, names_to: "id" }, cols)).toBeNull(); // 'id' vira linha, então o nome fica livre
    expect(stepProblem({ ...u, values_to: "VARIAVEL" }, cols)).toMatch(/não podem repetir/); // igual ao outro nome novo (sem diferenciar maiúsculas)
  });
  it("mesclar e acrescentar exigem o outro dataset", () => {
    const j = defaultStep("join", cols, "") as S<"join">;
    expect(stepProblem(j, cols)).toMatch(/outro dataset/);
    expect(stepProblem({ ...j, other_id: "x" }, cols)).toMatch(/dois lados/);
    expect(stepProblem({ ...j, other_id: "x", keys: [{ left: "id", right: "codigo" }] }, cols)).toBeNull();
    const a = defaultStep("append", cols, "x") as S<"append">;
    expect(a.other_id).toBe("x");
    expect(stepProblem(a, cols)).toBeNull();
    expect(stepProblem({ ...a, source_column: "lote", label_current: "a", label_other: "a" }, cols)).toMatch(/diferentes/);
    expect(stepProblem({ ...a, source_column: "lote", label_current: "a", label_other: "b" }, cols)).toBeNull();
    expect(cleanStep({ ...a, source_column: "  " }).op).toBe("append");
    expect((cleanStep({ ...a, source_column: "  " }) as S<"append">).source_column).toBeUndefined();
  });
});
