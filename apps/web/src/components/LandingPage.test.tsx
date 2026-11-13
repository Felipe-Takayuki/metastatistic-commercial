import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";

describe("LandingPage", () => {
  it("renderiza os elementos principais da Landing Page", () => {
    const onOpenAuth = vi.fn();
    const html = renderToStaticMarkup(<LandingPage onOpenAuth={onOpenAuth} />);

    // Brand e badges
    expect(html).toContain("Metastatistic");
    expect(html).toContain("Enterprise");
    expect(html).not.toContain("Enterprise SaaS");

    // Hero title & subtitle
    expect(html).toContain("A agilidade visual do Business Intelligence");
    expect(html).toContain("rigor científico");
    expect(html).toContain("Metabase");
    expect(html).toContain("JASP");

    // Vitrine APA 7th
    expect(html).toContain("APA 7th Format");
    expect(html).toContain("Tabela 1.");
    expect(html).toContain("Teste t para Amostras Independentes");
    expect(html).toContain("BF₁₀");

    // 4 Pilares
    expect(html).toContain("Catálogo Estatístico Frequentista &amp; Bayesiano");
    expect(html).toContain("Data Prep Visual sem Código (DuckDB &amp; Arrow)");
    expect(html).toContain("Relatórios APA 7th &amp; Dashboards Vivos");
    expect(html).toContain("Segurança &amp; Governança Enterprise");

    // Seção comparativa
    expect(html).toContain("Benchmark de Mercado");
    expect(html).toContain("Power BI / Tableau / Metabase");
    expect(html).toContain("SPSS / JASP / RStudio");

    // Seção de conformidade
    expect(html).toContain("FDA 21 CFR Part 11");
    expect(html).toContain("SOC 2 Type II Ready");
    expect(html).toContain("SSO &amp; SCIM 2.0");

    // Planos
    expect(html).toContain("Free");
    expect(html).toContain("Pro");
    expect(html).toContain("R$ 0");
    expect(html).toContain("R$ 249");
    expect(html).not.toContain("US$");
    expect(html).not.toContain("Faturamento Anual");
  });
});
