import { describe, expect, it } from "vitest";
import { actionLabel, describeEvent, isAlert } from "./audit";

const ev = (over: object) => ({ id: 1, ts: "", user_id: null, username: "ana", action: "create", kind: "report", target: "x", detail: "Meu relatório", ...over });

describe("auditoria", () => {
  it("descreve ação, tipo e detalhe", () => expect(describeEvent(ev({}))).toBe("Criou relatório · Meu relatório"));
  it("sem tipo nem detalhe fica só a ação", () => expect(describeEvent(ev({ action: "logout", kind: null, detail: null }))).toBe("Saiu"));
  it("ação desconhecida aparece como veio", () => expect(actionLabel("coisa_nova")).toBe("coisa_nova"));
  it("destaca o que foi barrado", () => {
    expect(isAlert("denied")).toBe(true);
    expect(isAlert("login")).toBe(false);
  });
});
