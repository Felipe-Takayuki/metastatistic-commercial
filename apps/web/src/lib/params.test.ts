import { describe, expect, it } from "vitest";
import type { DashFilter } from "../api";
import { filterProblems, literal, paramsIn, reconcileValues, sanitizeName, substitute } from "./params";

const F = (name: string, type: DashFilter["type"], def = ""): DashFilter => ({ name, label: "", type, default: def });

describe("literal", () => {
  it("vazio vira NULL em qualquer tipo", () => {
    for (const t of ["text", "number", "date"] as const) expect(literal(F("a", t), "  ")).toEqual({ sql: "NULL" });
  });
  it("texto: aspas simples duplicadas — o valor nunca escapa do literal", () => {
    expect(literal(F("a", "text"), "O'Brien")).toEqual({ sql: "'O''Brien'" });
    expect(literal(F("a", "text"), "x'; DROP TABLE t; --")).toEqual({ sql: "'x''; DROP TABLE t; --'" });
    expect(literal(F("a", "text"), "a\0b")).toEqual({ sql: "'ab'" });
  });
  it("número: aceita vírgula decimal e sinal; rejeita qualquer outra coisa (inclusive injeção)", () => {
    expect(literal(F("a", "number"), "-3,5")).toEqual({ sql: "-3.5" });
    expect(literal(F("a", "number"), "10")).toEqual({ sql: "10" });
    for (const bad of ["1e5", "1; DROP", "abc", "1 OR 1=1", "0x10", "1.2.3"]) expect(literal(F("a", "number"), bad)).toHaveProperty("error");
  });
  it("data: AAAA-MM-DD existente; rejeita dia inexistente e formatos soltos", () => {
    expect(literal(F("a", "date"), "2024-02-29")).toEqual({ sql: "DATE '2024-02-29'" });
    for (const bad of ["2023-02-29", "2024-13-01", "01/02/2024", "2024-1-1", "2024-01-01'; --"]) expect(literal(F("a", "date"), bad)).toHaveProperty("error");
  });
});

describe("paramsIn / substitute", () => {
  const filters = [F("grupo", "text"), F("minimo", "number", "5")];
  it("lista os parâmetros sem repetição", () => {
    expect(paramsIn("SELECT {{ grupo }}, {{grupo}}, {{minimo}}")).toEqual(["grupo", "minimo"]);
    expect(paramsIn("SELECT 1")).toEqual([]);
  });
  it("substitui todas as ocorrências; sem valor usa o padrão do filtro", () => {
    const r = substitute(`SELECT * FROM t WHERE ({{grupo}} IS NULL OR g = {{grupo}}) AND n >= {{minimo}}`, filters, { grupo: "a" });
    expect(r).toEqual({ sql: `SELECT * FROM t WHERE ('a' IS NULL OR g = 'a') AND n >= 5` });
    expect(substitute("SELECT {{grupo}}", filters, {})).toEqual({ sql: "SELECT NULL" });
  });
  it("o valor digitado não é re-substituído (sem injeção de outro parâmetro)", () => {
    expect(substitute("SELECT {{grupo}}", filters, { grupo: "{{minimo}}" })).toEqual({ sql: "SELECT '{{minimo}}'" });
  });
  it("filtro desconhecido ou valor inválido vira erro (o tile não consulta)", () => {
    expect(substitute("SELECT {{nada}}", filters, {})).toHaveProperty("error");
    expect(substitute("SELECT {{minimo}}", filters, { minimo: "x" })).toHaveProperty("error");
  });
  it("SQL sem parâmetros passa intacto", () => {
    expect(substitute("SELECT '{ não é }' AS a", filters, {})).toEqual({ sql: "SELECT '{ não é }' AS a" });
  });
});

describe("reconcileValues / sanitizeName / filterProblems", () => {
  it("mantém o digitado, usa o padrão nos novos e descarta os removidos", () => {
    expect(reconcileValues([F("a", "text", "x"), F("b", "text", "y")], { a: "digitado", z: "velho" })).toEqual({ a: "digitado", b: "y" });
  });
  it("nome de filtro vira identificador válido", () => {
    expect(sanitizeName("meu filtro-1")).toBe("meu_filtro_1");
    expect(sanitizeName("1abc")).toBe("_1abc");
    expect(sanitizeName("ação")).toBe("a__o");
    expect(sanitizeName("x".repeat(60))).toHaveLength(40);
  });
  it("aponta nome vazio e repetido", () => {
    expect(filterProblems([F("a", "text"), F("b", "text")])).toEqual([]);
    expect(filterProblems([F("a", "text"), F("a", "date")])).toEqual(["Nome de filtro repetido: a."]);
    expect(filterProblems([F("", "text")])).toEqual(["Há um filtro sem nome."]);
  });
});
