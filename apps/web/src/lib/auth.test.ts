import { describe, expect, it } from "vitest";
import { credentialProblem, roleCan } from "./auth";

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
