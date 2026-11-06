import { describe, expect, it } from "vitest";
import type { Dataset, QueryBuilder } from "../api";
import { buildSql, builderProblem, chartFor, defaultBuilder, describeBuilder, measureAliases, repair } from "./builder";

const col = (name: string, dtype: string, n_distinct: number | null = null) => ({ name, dtype, measurement: (dtype === "VARCHAR" ? "nominal" : "scale") as "nominal" | "scale", n_distinct });
const ds: Dataset = {
  id: "d1", name: "vendas.csv", table_name: "vendas", n_rows: 100, created_at: "",
  columns: [col("regiao", "VARCHAR", 4), col("data", "DATE", 30), col("receita", "DOUBLE"), col("qtd", "BIGINT")],
};
const other: Dataset = { ...ds, id: "d2", table_name: "outro", columns: [col("tipo", "VARCHAR", 3), col("valor", "DOUBLE")] };
const summary = (over: Partial<QueryBuilder> = {}): QueryBuilder => ({ dataset_id: "d1", kind: "summary", group_by: "regiao", measures: [{ fn: "mean", column: "receita" }], ...over });

describe("buildSql", () => {
  it("resumo por categoria: uma linha por valor, ordenada, sem categorias vazias", () => {
    expect(buildSql(summary(), ds)).toBe('SELECT "regiao", round(avg("receita"), 2) AS "média de receita" FROM "vendas" WHERE "regiao" IS NOT NULL GROUP BY 1 ORDER BY 1');
  });
  it("cada cálculo vira a função certa; até 3 colunas de valor", () => {
    const sql = buildSql(summary({ measures: [{ fn: "count", column: "" }, { fn: "sum", column: "qtd" }, { fn: "median", column: "receita" }] }), ds);
    expect(sql).toContain('count(*) AS "linhas"');
    expect(sql).toContain('sum("qtd") AS "soma de qtd"');
    expect(sql).toContain('round(median("receita"), 2) AS "mediana de receita"');
  });
  it("duas medidas iguais ganham nomes diferentes (o resultado não pode ter colunas repetidas)", () => {
    expect(measureAliases([{ fn: "mean", column: "receita" }, { fn: "mean", column: "receita" }])).toEqual(["média de receita", "média de receita 2"]);
  });
  it("KPI sem categoria: uma linha só", () => {
    expect(buildSql({ dataset_id: "d1", kind: "summary", group_by: "", measures: [{ fn: "sum", column: "receita" }] }, ds)).toBe('SELECT sum("receita") AS "soma de receita" FROM "vendas"');
  });
  it("pontos: valores brutos com X e Y preenchidos, no máximo 5000", () => {
    expect(buildSql({ dataset_id: "d1", kind: "points", group_by: "qtd", measures: [{ fn: "value", column: "receita" }] }, ds))
      .toBe('SELECT "qtd", "receita" AS "receita" FROM "vendas" WHERE "qtd" IS NOT NULL AND "receita" IS NOT NULL LIMIT 5000');
  });
  it("nomes com aspas são escapados (nada de SQL injetado por um nome de coluna)", () => {
    const evil: Dataset = { ...ds, table_name: 'a"b', columns: [col('x"; DROP', "VARCHAR", 2), col("v", "DOUBLE")] };
    const sql = buildSql({ dataset_id: "d1", kind: "summary", group_by: 'x"; DROP', measures: [{ fn: "mean", column: "v" }] }, evil);
    expect(sql).toContain('"x""; DROP"');
    expect(sql).toContain('FROM "a""b"');
  });
});

describe("builderProblem", () => {
  it("pronto quando dataset, categoria e cálculo existem", () => expect(builderProblem(summary(), ds, "chart")).toBeNull());
  it("diz o que falta", () => {
    expect(builderProblem(summary(), undefined, "chart")).toMatch(/dataset/);
    expect(builderProblem(summary({ group_by: "" }), ds, "chart")).toMatch(/categorias/);
    expect(builderProblem(summary({ measures: [{ fn: "mean", column: "" }] }), ds, "chart")).toMatch(/coluna de cada cálculo/);
  });
  it("média/soma exigem número; mínimo, máximo e contagem aceitam qualquer coluna", () => {
    expect(builderProblem(summary({ measures: [{ fn: "mean", column: "regiao" }] }), ds, "chart")).toMatch(/não é numérica/);
    expect(builderProblem(summary({ measures: [{ fn: "max", column: "regiao" }] }), ds, "chart")).toBeNull();
    expect(builderProblem(summary({ measures: [{ fn: "count", column: "" }] }), ds, "chart")).toBeNull();
  });
  it("dispersão exige número nos dois eixos", () => {
    const pts = (x: string, y: string): QueryBuilder => ({ dataset_id: "d1", kind: "points", group_by: x, measures: [{ fn: "value", column: y }] });
    expect(builderProblem(pts("qtd", "receita"), ds, "chart")).toBeNull();
    expect(builderProblem(pts("regiao", "receita"), ds, "chart")).toMatch(/dois eixos/);
    expect(builderProblem(pts("qtd", "regiao"), ds, "chart")).toMatch(/eixo Y precisa/);
  });
  it("KPI não precisa de categoria", () => expect(builderProblem({ dataset_id: "d1", kind: "summary", group_by: "", measures: [{ fn: "count", column: "" }] }, ds, "kpi")).toBeNull());
});

describe("defaultBuilder / repair / chartFor", () => {
  it("gráfico: média da 1ª coluna numérica pela 1ª categoria com poucos valores", () => {
    expect(defaultBuilder("chart", ds)).toEqual({ dataset_id: "d1", kind: "summary", group_by: "regiao", measures: [{ fn: "mean", column: "receita" }] });
  });
  it("sem coluna numérica cai na contagem; KPI começa contando linhas", () => {
    const text: Dataset = { ...ds, columns: [col("a", "VARCHAR", 3), col("b", "VARCHAR", 3)] };
    expect(defaultBuilder("chart", text).measures).toEqual([{ fn: "count", column: "" }]);
    expect(defaultBuilder("kpi", ds).measures).toEqual([{ fn: "count", column: "" }]);
  });
  it("trocar de dataset troca só o que deixou de existir", () => {
    const r = repair(summary(), other, "chart");
    expect(r).toMatchObject({ dataset_id: "d2", group_by: "tipo", measures: [{ fn: "mean", column: "valor" }] });
    expect(repair(summary({ group_by: "regiao" }), ds, "chart").group_by).toBe("regiao");
  });
  it("o gráfico acompanha: barras por padrão, linha para data, dispersão para pontos", () => {
    expect(chartFor(summary(), ds, null)).toMatchObject({ type: "bar", x: "regiao", ys: ["média de receita"] });
    expect(chartFor(summary({ group_by: "data" }), ds, null).type).toBe("line");
    expect(chartFor(summary(), ds, { type: "line", x: "regiao", ys: [], slots: {} }).type).toBe("line"); // respeita a escolha do usuário
    expect(chartFor({ dataset_id: "d1", kind: "points", group_by: "qtd", measures: [{ fn: "value", column: "receita" }] }, ds, null).type).toBe("scatter");
  });
  it("descreve em português", () => expect(describeBuilder(summary())).toBe("média de receita por regiao"));
});
