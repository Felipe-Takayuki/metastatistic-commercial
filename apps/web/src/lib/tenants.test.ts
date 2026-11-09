import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  getActiveTenant,
  getActiveTenantId,
  getRecentTenants,
  setActiveTenant,
} from "../api";

describe("Multi-Tenancy Frontend Module", () => {
  // Mock simples de localStorage para ambiente node
  const store: Record<string, string> = {};
  const mockLocalStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const k in store) delete store[k];
    },
  };

  beforeEach(() => {
    mockLocalStorage.clear();
    vi.stubGlobal("localStorage", mockLocalStorage);
  });

  it("possui todos os métodos de API de tenants declarados", () => {
    expect(typeof api.createTenant).toBe("function");
    expect(typeof api.getTenant).toBe("function");
    expect(typeof api.getTenantBySlug).toBe("function");
    expect(typeof api.listTenantMembers).toBe("function");
    expect(typeof api.createTenantInvitation).toBe("function");
  });

  it("retorna o tenant default quando o storage está vazio", () => {
    const active = getActiveTenant();
    expect(active.id).toBe("default");
    expect(active.name).toBe("Metastatistic");
    expect(getActiveTenantId()).toBe("default");
  });

  it("salva e recupera o tenant ativo corretamente", () => {
    setActiveTenant({
      id: "tenant_clinica_abc",
      name: "Clínica ABC",
      slug: "clinica-abc",
      tier: "team",
    });

    const active = getActiveTenant();
    expect(active.id).toBe("tenant_clinica_abc");
    expect(active.name).toBe("Clínica ABC");
    expect(active.slug).toBe("clinica-abc");
    expect(active.tier).toBe("team");
    expect(getActiveTenantId()).toBe("tenant_clinica_abc");
  });

  it("mantém a lista de organizações recentes atualizada", () => {
    setActiveTenant({ id: "t1", name: "Org 1", slug: "org-1", tier: "community" });
    setActiveTenant({ id: "t2", name: "Org 2", slug: "org-2", tier: "team" });

    const recents = getRecentTenants();
    expect(recents.length).toBe(2);
    expect(recents[0].id).toBe("t2");
    expect(recents[1].id).toBe("t1");
  });

  it("injeta o cabeçalho X-Tenant-ID com o tenant ativo nas requisições HTTP", async () => {
    setActiveTenant({ id: "tenant_medical_hospital", name: "Hospital", tier: "enterprise" });

    let capturedHeaders: Headers | undefined;
    const originalFetch = globalThis.fetch;
    const mockFetch = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    vi.stubGlobal("fetch", mockFetch);

    try {
      await api.listDatasets();
      expect(mockFetch).toHaveBeenCalled();
      expect(capturedHeaders?.get("X-Tenant-ID")).toBe("tenant_medical_hospital");
    } finally {
      vi.stubGlobal("fetch", originalFetch);
    }
  });
});
