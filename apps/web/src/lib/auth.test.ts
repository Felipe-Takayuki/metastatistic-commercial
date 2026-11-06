import { describe, expect, it } from "vitest";
import { credentialProblem, formatAttributes, parseAttributes, roleCan } from "./auth";

describe("roleCan", () => {
  it("cada papel inclui os anteriores", () => {
    expect(roleCan("viewer", "viewer")).toBe(true);
    expect(roleCan("viewer", "editor")).toBe(false);
    expect(roleCan("editor", "viewer")).toBe(true);
    expect(roleCan("editor", "admin")).toBe(false);
    expect(roleCan("admin", "editor")).toBe(true);
  });
  it("sem papel não pode nada", () => expect(roleCan(undefined, "viewer")).toBe(false));
});

describe("credentialProblem", () => {
  it("aceita usuário e senha válidos", () => expect(credentialProblem("ana", "12345678")).toBeNull());
  it("recusa usuário curto ou com espaço", () => {
    expect(credentialProblem("an", "12345678")).not.toBeNull();
    expect(credentialProblem("a na", "12345678")).not.toBeNull();
  });
  it("recusa senha curta", () => expect(credentialProblem("ana", "1234567")).toMatch(/8/));
});

describe("atributos de usuário", () => {
  it("lê nome=valor separados por ponto e vírgula, com vários valores por vírgula", () => {
    expect(parseAttributes("Regiao = Sul , Norte ; setor=A")).toEqual({ regiao: "Sul,Norte", setor: "A" });
  });
  it("ignora partes sem '=' ou sem valor", () => expect(parseAttributes("solto; vazio=; ok=1,,2")).toEqual({ ok: "1,2" }));
  it("ida e volta", () => expect(parseAttributes(formatAttributes({ regiao: "Sul,Norte", setor: "A" }))).toEqual({ regiao: "Sul,Norte", setor: "A" }));
  it("sem atributos vira texto vazio", () => expect(formatAttributes(undefined)).toBe(""));
});
