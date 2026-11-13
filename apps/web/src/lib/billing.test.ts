import { describe, expect, it } from "vitest";
import { api } from "../api";
import { eventLabel, formatBRL, planName } from "./billing";

describe("billing api methods", () => {
  it("tem métodos de api de billing declarados", () => {
    expect(typeof api.getBillingPlans).toBe("function");
    expect(typeof api.getSubscription).toBe("function");
    expect(typeof api.createCheckoutSession).toBe("function");
    expect(typeof api.createPortalSession).toBe("function");
  });
});

describe("billing helpers", () => {
  it("formata centavos em reais", () => {
    expect(formatBRL(24900).replace(/\s/g, " ")).toBe("R$ 249,00");
    expect(formatBRL(0).replace(/\s/g, " ")).toBe("R$ 0,00");
  });
  it("traduz o tier interno para o nome do plano", () => {
    expect(planName("community")).toBe("Free");
    expect(planName("team")).toBe("Pro");
    expect(planName("enterprise")).toBe("Enterprise");
  });
  it("rotula os eventos do Stripe e deixa os desconhecidos como estão", () => {
    expect(eventLabel("invoice.payment_failed")).toBe("Pagamento falhou");
    expect(eventLabel("charge.refunded")).toBe("charge.refunded");
  });
});
