import { describe, expect, it } from "vitest";
import { api } from "../api";

describe("billing api methods", () => {
  it("tem métodos de api de billing declarados", () => {
    expect(typeof api.getBillingPlans).toBe("function");
    expect(typeof api.getSubscription).toBe("function");
    expect(typeof api.createCheckoutSession).toBe("function");
    expect(typeof api.createPortalSession).toBe("function");
  });
});
