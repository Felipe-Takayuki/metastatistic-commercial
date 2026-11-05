import { describe, expect, it } from "vitest";
import { pivotColumnGroups } from "./pivot";

// Tabela real "Chi-Squared Tests" do jaspFrequencies (conferida com o R: X²=6.867, gl=2, p=.032, N=80).
const chi = {
  schema: { fields: [
    { name: "type[chiSquared]", title: "", type: "string" },
    { name: "value[chiSquared]", title: "Value", type: "number", format: "sf:4;dp:3" },
    { name: "df[chiSquared]", title: "df", type: "integer" },
    { name: "p[chiSquared]", title: "p", type: "pvalue", format: "dp:3;p:.001" },
    { name: "type[N]", title: "", type: "string" },
    { name: "value[N]", title: "Value", type: "integer" },
    { name: "df[N]", title: "df", type: "integer" },
    { name: "p[N]", title: "p", type: "pvalue", format: "dp:3;p:.001" },
  ] },
  data: [{ "type[chiSquared]": "Χ²", "value[chiSquared]": 6.86666666666667, "df[chiSquared]": 2, "p[chiSquared]": 0.0322791640313599,
           "type[N]": "N", "value[N]": 80, "df[N]": "", "p[N]": "" }],
};

describe("pivotColumnGroups", () => {
  it("transpõe grupos de colunas em linhas e formata cada célula com o formato da própria coluna", () => {
    const out = pivotColumnGroups(chi)!;
    expect(out.fields.map((f) => f.name)).toEqual(["type", "value", "df", "p"]);
    expect(out.fields.map((f) => f.title)).toEqual(["", "Value", "df", "p"]);
    expect(out.data).toEqual([
      { type: "Χ²", value: "6.867", df: "2", p: ".032" },
      { type: "N", value: "80", df: "", p: "" },   // N inteiro (não "80.000"); df e p vazios
    ]);
  });
  it("tabela com coluna comum (sem colchetes) fica como veio", () => {
    const t = { schema: { fields: [{ name: "grupo", type: "string" }, { name: "alto[counts]", type: "integer" }, { name: "baixo[counts]", type: "integer" }] }, data: [{ grupo: "a", "alto[counts]": 1, "baixo[counts]": 2 }] };
    expect(pivotColumnGroups(t)).toBeNull();
  });
  it("com várias linhas, um só grupo ou grupo sem `type` não transpõe", () => {
    expect(pivotColumnGroups({ ...chi, data: [chi.data[0], chi.data[0]] })).toBeNull();
    const one = { schema: { fields: chi.schema.fields.slice(0, 4) }, data: chi.data };
    expect(pivotColumnGroups(one)).toBeNull();
    const noType = { schema: { fields: chi.schema.fields.filter((f) => f.name !== "type[N]") }, data: chi.data };
    expect(pivotColumnGroups(noType)).toBeNull();
  });
  it("valor NaN do JASP aparece como texto, sem quebrar", () => {
    const t = { schema: { fields: [
      { name: "type[PhiCoef]", type: "string" }, { name: "value[PhiCoef]", type: "number", format: "sf:4;dp:3" },
      { name: "type[CramerV]", type: "string" }, { name: "value[CramerV]", type: "number", format: "sf:4;dp:3" } ] },
      data: [{ "type[PhiCoef]": "Phi-coefficient", "value[PhiCoef]": "NaN", "type[CramerV]": "Cramer's V ", "value[CramerV]": 0.292973263854116 }] };
    expect(pivotColumnGroups(t)!.data).toEqual([{ type: "Phi-coefficient", value: "NaN" }, { type: "Cramer's V ", value: "0.293" }]);
  });
});
