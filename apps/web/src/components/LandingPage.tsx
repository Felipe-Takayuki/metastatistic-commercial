import { useState, useEffect } from "react";
import { applyThemeMode, loadThemeMode, type ThemeMode } from "../lib/theme";

interface LandingPageProps {
  onOpenAuth: (tab: "login" | "register") => void;
}

const THEME_LABEL: Record<ThemeMode, string> = {
  auto: "Tema: Auto",
  light: "Tema: Claro",
  dark: "Tema: Escuro",
};

const NEXT_THEME: Record<ThemeMode, ThemeMode> = {
  auto: "light",
  light: "dark",
  dark: "auto",
};

export function LandingPage({ onOpenAuth }: LandingPageProps) {
  const [theme, setTheme] = useState<ThemeMode>(loadThemeMode);
  const [pricingPeriod, setPricingPeriod] = useState<"monthly" | "yearly">("yearly");
  const [activeTab, setActiveTab] = useState<"ttest" | "anova" | "bayes">("ttest");

  useEffect(() => {
    applyThemeMode(theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => NEXT_THEME[prev]);
  };

  return (
    <div className="landing-page">
      {/* 1. Header / Navbar Sticky */}
      <header className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-brand">
            <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true" className="landing-brand-logo">
              <rect x="5" y="15" width="5" height="12" rx="1.5" fill="var(--series-1)" />
              <rect x="13.5" y="7" width="5" height="20" rx="1.5" fill="var(--series-2)" />
              <rect x="22" y="11" width="5" height="16" rx="1.5" fill="var(--series-3)" />
            </svg>
            <span className="landing-brand-name">Metastatistic</span>
            <span className="landing-brand-badge">Enterprise</span>
          </div>

          <nav className="landing-nav-links" aria-label="Navegação da página">
            <a href="#recursos">Recursos</a>
            <a href="#ciencia">Rigor Científico</a>
            <a href="#seguranca">Governança</a>
            <a href="#planos">Planos</a>
          </nav>

          <div className="landing-nav-actions">
            <button
              type="button"
              className="btn ghost sm landing-theme-toggle"
              onClick={toggleTheme}
              title="Alternar tema de cores"
            >
              {THEME_LABEL[theme]}
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => onOpenAuth("login")}
            >
              Entrar
            </button>
            <button
              type="button"
              className="btn primary sm"
              onClick={() => onOpenAuth("register")}
            >
              Criar Conta Grátis
            </button>
          </div>
        </div>
      </header>

      {/* 2. Hero Section */}
      <section className="landing-hero">
        <div className="landing-hero-badge">
          <span className="landing-pulse-dot" />
          BI Corporativo + Ciência Estatística Frequentista & Bayesiana
        </div>

        <h1 className="landing-hero-title">
          A agilidade visual do Business Intelligence com o{" "}
          <span className="landing-gradient-text">rigor científico</span> da análise estatística.
        </h1>

        <p className="landing-hero-subtitle">
          Unimos a intuitividade e preparação de dados sem código (DNA <strong>Metabase</strong>)
          à precisão editorial de inferência e relatórios estritos no padrão APA 7th (DNA <strong>JASP</strong>).
          Execute análises frequentistas e bayesianas em segundos sobre petabytes com motor DuckDB e Apache Arrow.
        </p>

        <div className="landing-hero-cta">
          <button
            type="button"
            className="btn primary lg landing-hero-btn"
            onClick={() => onOpenAuth("register")}
          >
            Começar Gratuitamente
          </button>
          <button
            type="button"
            className="btn lg"
            onClick={() => onOpenAuth("login")}
          >
            Já tenho uma conta
          </button>
          <a href="#planos" className="landing-pricing-link">
            Ver Planos e Preços →
          </a>
        </div>

        {/* 3. Vitrine Visual / Mockup Interativo APA 7th & Data Viz */}
        <div className="landing-showcase-wrapper">
          <div className="landing-showcase card">
            <div className="landing-showcase-header">
              <div className="landing-window-dots">
                <span className="dot red" />
                <span className="dot yellow" />
                <span className="dot green" />
              </div>
              <div className="landing-showcase-tabs">
                <button
                  type="button"
                  className={`landing-tab-btn ${activeTab === "ttest" ? "active" : ""}`}
                  onClick={() => setActiveTab("ttest")}
                >
                  Teste t Independente (Student & Bayes)
                </button>
                <button
                  type="button"
                  className={`landing-tab-btn ${activeTab === "anova" ? "active" : ""}`}
                  onClick={() => setActiveTab("anova")}
                >
                  ANOVA Unifatorial & Post-Hoc
                </button>
                <button
                  type="button"
                  className={`landing-tab-btn ${activeTab === "bayes" ? "active" : ""}`}
                  onClick={() => setActiveTab("bayes")}
                >
                  Regressão & Fator de Bayes (BF₁₀)
                </button>
              </div>
              <div className="landing-showcase-tag">APA 7th Format</div>
            </div>

            <div className="landing-showcase-content">
              {activeTab === "ttest" && (
                <div className="landing-demo-body">
                  <div className="landing-demo-top">
                    <div>
                      <h4 className="landing-demo-title">
                        Tabela 1. <em>Resultados do Teste t para Amostras Independentes</em>
                      </h4>
                      <p className="landing-demo-sub">
                        Comparação de biomarcadores plasmáticos entre Grupo Tratamento (n = 30) e Grupo Controle (n = 30)
                      </p>
                    </div>
                    <span className="chip" style={{ background: "var(--accent-wash)", color: "var(--accent)", fontWeight: 600 }}>
                      BF₁₀ = 42.84 (Evidência Muito Forte)
                    </span>
                  </div>

                  <div className="landing-table-responsive">
                    <table className="apa-table landing-apa-sample">
                      <thead>
                        <tr>
                          <th className="left">Variável Dependente</th>
                          <th><em>t</em></th>
                          <th><em>gl</em></th>
                          <th><em>p</em></th>
                          <th>Diferença de Médias</th>
                          <th><em>d</em> de Cohen</th>
                          <th>IC 95% <em>d</em></th>
                          <th>BF₁₀</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="left">Concentração de Proteína (mg/dL)</td>
                          <td>4.12</td>
                          <td>58</td>
                          <td>&lt; .001</td>
                          <td>14.85</td>
                          <td>1.06</td>
                          <td>[0.51, 1.61]</td>
                          <td>42.84</td>
                        </tr>
                        <tr>
                          <td className="left">Tempo de Recuperação Celular (h)</td>
                          <td>-3.48</td>
                          <td>58</td>
                          <td>.001</td>
                          <td>-9.20</td>
                          <td>-0.90</td>
                          <td>[-1.43, -0.36]</td>
                          <td>18.15</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="apa-notes landing-apa-footnote">
                    <em>Nota.</em> Testes bicaudais com premissa de variâncias homogêneas (teste de Levene, <em>p</em> = .342).
                    Fatores de Bayes calculados com prior de Cauchy padrão <em>r</em> = 0.707.
                  </div>

                  {/* Dataviz SVG Mockup */}
                  <div className="landing-viz-container">
                    <div className="landing-viz-header">
                      <strong>Intervalos de Confiança (95% CI) e Densidade das Amostras</strong>
                      <span className="muted small">Plotagem reativa ECharts / SVG vectorial</span>
                    </div>
                    <div className="landing-svg-chart">
                      <svg viewBox="0 0 680 160" width="100%" height="160" aria-label="Gráfico de Intervalo de Confiança">
                        <line x1="50" y1="130" x2="630" y2="130" stroke="var(--axis)" strokeWidth="1.5" />
                        
                        {/* Eixo X labels */}
                        <text x="50" y="150" fill="var(--text-secondary)" fontSize="12" textAnchor="middle">20</text>
                        <text x="195" y="150" fill="var(--text-secondary)" fontSize="12" textAnchor="middle">40</text>
                        <text x="340" y="150" fill="var(--text-secondary)" fontSize="12" textAnchor="middle">60</text>
                        <text x="485" y="150" fill="var(--text-secondary)" fontSize="12" textAnchor="middle">80</text>
                        <text x="630" y="150" fill="var(--text-secondary)" fontSize="12" textAnchor="middle">100 (mg/dL)</text>

                        {/* Grade Vertical */}
                        <line x1="195" y1="20" x2="195" y2="130" stroke="var(--grid)" strokeDasharray="3 3" />
                        <line x1="340" y1="20" x2="340" y2="130" stroke="var(--grid)" strokeDasharray="3 3" />
                        <line x1="485" y1="20" x2="485" y2="130" stroke="var(--grid)" strokeDasharray="3 3" />

                        {/* Grupo Controle (Series 1) */}
                        <g>
                          {/* Barra de Erro */}
                          <line x1="260" y1="50" x2="380" y2="50" stroke="var(--series-1)" strokeWidth="2.5" />
                          <line x1="260" y1="42" x2="260" y2="58" stroke="var(--series-1)" strokeWidth="2" />
                          <line x1="380" y1="42" x2="380" y2="58" stroke="var(--series-1)" strokeWidth="2" />
                          {/* Ponto Médio */}
                          <circle cx="320" cy="50" r="6" fill="var(--series-1)" />
                          <text x="140" y="54" fill="var(--text-primary)" fontSize="13" fontWeight="600">Controle: M = 48.2</text>
                          <text x="400" y="54" fill="var(--text-secondary)" fontSize="12">95% CI [42.1, 54.3]</text>
                        </g>

                        {/* Grupo Tratamento (Series 2) */}
                        <g>
                          {/* Barra de Erro */}
                          <line x1="410" y1="95" x2="520" y2="95" stroke="var(--series-2)" strokeWidth="2.5" />
                          <line x1="410" y1="87" x2="410" y2="103" stroke="var(--series-2)" strokeWidth="2" />
                          <line x1="520" y1="87" x2="520" y2="103" stroke="var(--series-2)" strokeWidth="2" />
                          {/* Ponto Médio */}
                          <circle cx="465" cy="95" r="6" fill="var(--series-2)" />
                          <text x="140" y="99" fill="var(--text-primary)" fontSize="13" fontWeight="600">Tratamento: M = 63.1</text>
                          <text x="535" y="99" fill="var(--text-secondary)" fontSize="12">95% CI [57.8, 68.4]</text>
                        </g>
                      </svg>
                    </div>
                  </div>

                  {/* Bloco de Síntese Automatizada */}
                  <div className="landing-narrative-box">
                    <div className="landing-narrative-badge">Interpretação Narrativa Automatizada (APA 7th)</div>
                    <p>
                      Um teste <em>t</em> para amostras independentes revelou uma diferença estatisticamente significante
                      na concentração de proteína entre os grupos, com o grupo <strong>Tratamento</strong> (<em>M</em> = 63.1, <em>DP</em> = 9.8)
                      apresentando escores substancialmente superiores ao <strong>Controle</strong> (<em>M</em> = 48.2, <em>DP</em> = 11.2),
                      <em> t</em>(58) = 4.12, <em>p</em> &lt; .001, <em>d</em> = 1.06, IC 95% [0.51, 1.61].
                      A análise bayesiana confirmou evidência muito forte a favor da hipótese alternativa
                      (<em>BF</em>₁₀ = 42.84), indicando que os dados observados são aproximadamente 43 vezes mais prováveis
                      sob a hipótese de efeito real em relação ao modelo nulo.
                    </p>
                  </div>
                </div>
              )}

              {activeTab === "anova" && (
                <div className="landing-demo-body">
                  <div className="landing-demo-top">
                    <div>
                      <h4 className="landing-demo-title">
                        Tabela 2. <em>ANOVA Unifatorial: Comparação Multigrupos</em>
                      </h4>
                      <p className="landing-demo-sub">Diferenças entre Doses (Placebo, 10mg, 25mg, 50mg) com correções de Welch</p>
                    </div>
                    <span className="chip" style={{ background: "var(--accent-wash)", color: "var(--accent)", fontWeight: 600 }}>
                      η² parcial = 0.28 (Efeito Grande)
                    </span>
                  </div>

                  <div className="landing-table-responsive">
                    <table className="apa-table landing-apa-sample">
                      <thead>
                        <tr>
                          <th className="left">Fonte de Variação</th>
                          <th>Soma dos Quadrados</th>
                          <th><em>gl</em></th>
                          <th>Quadrado Médio</th>
                          <th><em>F</em></th>
                          <th><em>p</em></th>
                          <th>η² parcial</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="left">Dose Terapêutica</td>
                          <td>1428.4</td>
                          <td>3</td>
                          <td>476.13</td>
                          <td>14.88</td>
                          <td>&lt; .001</td>
                          <td>0.28</td>
                        </tr>
                        <tr>
                          <td className="left">Resíduos</td>
                          <td>3712.0</td>
                          <td>116</td>
                          <td>32.00</td>
                          <td>—</td>
                          <td>—</td>
                          <td>—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="apa-notes landing-apa-footnote">
                    <em>Nota.</em> Homogeneidade de variâncias confirmada (Levene <em>p</em> = .41). Post-hoc de Tukey indica que 50mg &gt; 10mg &gt; Placebo (<em>p</em> &lt; .01).
                  </div>

                  <div className="landing-narrative-box">
                    <div className="landing-narrative-badge">Interpretação Narrativa Automatizada</div>
                    <p>
                      A análise de variância (ANOVA) unifatorial demonstrou um efeito principal significativo da dosagem,
                      <em> F</em>(3, 116) = 14.88, <em>p</em> &lt; .001, η²<sub>p</sub> = .28. Comparações pareadas post-hoc
                      ajustadas pelo método HSD de Tukey confirmaram que a dose de 50mg resultou em ganhos clinicamente
                      superiores tanto à dose de 10mg (<em>p</em> = .003) quanto ao placebo (<em>p</em> &lt; .001).
                    </p>
                  </div>
                </div>
              )}

              {activeTab === "bayes" && (
                <div className="landing-demo-body">
                  <div className="landing-demo-top">
                    <div>
                      <h4 className="landing-demo-title">
                        Tabela 3. <em>Regressão Linear Múltipla com Fatores de Bayes</em>
                      </h4>
                      <p className="landing-demo-sub">Seleção de Modelos e Inclusão de Preditores (JASP/Metastatistic Engine)</p>
                    </div>
                    <span className="chip" style={{ background: "var(--accent-wash)", color: "var(--accent)", fontWeight: 600 }}>
                      BF_incluídos &gt; 100
                    </span>
                  </div>

                  <div className="landing-table-responsive">
                    <table className="apa-table landing-apa-sample">
                      <thead>
                        <tr>
                          <th className="left">Modelo Candidato</th>
                          <th>P(M)</th>
                          <th>P(M|dados)</th>
                          <th>BF_M</th>
                          <th>BF₁₀</th>
                          <th><em>R²</em></th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="left">Idade + Marcador A + Marcador B</td>
                          <td>0.20</td>
                          <td>0.74</td>
                          <td>11.38</td>
                          <td>184.2</td>
                          <td>0.54</td>
                        </tr>
                        <tr>
                          <td className="left">Idade + Marcador A</td>
                          <td>0.20</td>
                          <td>0.18</td>
                          <td>0.87</td>
                          <td>45.1</td>
                          <td>0.41</td>
                        </tr>
                        <tr>
                          <td className="left">Modelo Nulo (Intercepto Apenas)</td>
                          <td>0.20</td>
                          <td>0.001</td>
                          <td>0.004</td>
                          <td>1.0</td>
                          <td>0.00</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="apa-notes landing-apa-footnote">
                    <em>Nota.</em> Prior de modelo uniforme atribuído a todos os candidatos. Fator de Bayes em relação ao modelo nulo.
                  </div>

                  <div className="landing-narrative-box">
                    <div className="landing-narrative-badge">Interpretação Narrativa Automatizada</div>
                    <p>
                      A comparação bayesiana de modelos aponta o modelo completo (Idade + Marcador A + Marcador B)
                      como o mais plausível a posteriori (<em>P</em>(<em>M</em>|dados) = 0.74), superando o modelo nulo
                      por um fator de 184 vezes (<em>BF</em>₁₀ = 184.2). O modelo explica 54% da variância total da resposta (<em>R²</em> = .54).
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 4. Seção de Pilares e Recursos */}
      <section id="recursos" className="landing-section">
        <div className="landing-section-header">
          <span className="landing-section-tag">Capacidades da Plataforma</span>
          <h2 className="landing-section-title">Construído para Pesquisadores, Cientistas de Dados e Lideranças</h2>
          <p className="landing-section-desc">
            Chega de alternar entre planilhas frágeis, softwares legados dos anos 90 ou scripts dispersos.
            Uma infraestrutura unificada da ingestão à publicação científica.
          </p>
        </div>

        <div className="landing-grid">
          <div className="landing-card card">
            <div className="landing-card-icon" style={{ background: "var(--accent-wash)", color: "var(--accent)" }}>
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M12 20V10M18 20V4M6 20v-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3>Catálogo Estatístico Frequentista & Bayesiano</h3>
            <p>
              Execute testes paramétricos e não-paramétricos (testes t de Student, Welch e Mann-Whitney; ANOVA, ANCOVA,
              regressão linear/logística, correlações de Pearson e Spearman, qui-quadrado).
              Acesse Fatores de Bayes (BF₁₀, BF₀₁) e verificação automática de pressupostos (Shapiro-Wilk, Levene, Q-Q plots).
            </p>
            <ul className="landing-feature-list">
              <li>Testes t para amostras independentes e pareadas</li>
              <li>ANOVA Fatorial, Medidas Repetidas e ANCOVA</li>
              <li>Inferência Bayesiana com Priors Customizáveis</li>
            </ul>
          </div>

          <div className="landing-card card">
            <div className="landing-card-icon" style={{ background: "color-mix(in srgb, var(--series-2) 15%, transparent)", color: "var(--series-2)" }}>
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M4 7v10c0 2 1.5 3 3.5 3h9c2 0 3.5-1 3.5-3V7c0-2-1.5-3-3.5-3h-9C5.5 4 4 5 4 7z" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3>Data Prep Visual sem Código (DuckDB & Arrow)</h3>
            <p>
              Pipeline de transformação reativo em memória com DuckDB. Filtre por expressões lógicas, crie colunas calculadas,
              reordene, renomeie e deduplique dados com visualização de impacto em tempo real, sem necessidade de escrever consultas SQL.
            </p>
            <ul className="landing-feature-list">
              <li>Processamento vetorizado de alta performance</li>
              <li>Receitas de transformação auditáveis e reproduzíveis</li>
              <li>Conexão direta com CSV, Parquet e bases SQL</li>
            </ul>
          </div>

          <div className="landing-card card">
            <div className="landing-card-icon" style={{ background: "color-mix(in srgb, var(--series-3) 15%, transparent)", color: "var(--series-3)" }}>
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3>Relatórios APA 7th & Dashboards Vivos</h3>
            <p>
              Gere documentos prontos para submissão em periódicos indexados (Nature, Elsevier, Springer) ou apresentações executivas.
              Exportação com fidelidade tipográfica para PDF A4, Word (DOCX), LaTeX e Markdown, com narrativa científica gerada.
            </p>
            <ul className="landing-feature-list">
              <li>Tabelas com filetes APA e numerais tabulares</li>
              <li>Dashboards interativos com ECharts de baixa latência</li>
              <li>Exportação editorial com 1 clique</li>
            </ul>
          </div>

          <div className="landing-card card">
            <div className="landing-card-icon" style={{ background: "color-mix(in srgb, var(--accent) 15%, transparent)", color: "var(--accent)" }}>
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3>Segurança & Governança Enterprise</h3>
            <p>
              Arquitetura Multi-Tenant com isolamento lógico rígido, Single Sign-On corporativo (SAML 2.0 / OIDC),
              provisionamento SCIM 2.0 (Okta, Entra ID) e Trilha de Auditoria Imutável (SHA-256) compatível com FDA 21 CFR Part 11 e SOC 2.
            </p>
            <ul className="landing-feature-list">
              <li>Trilha imutável encadeada por hash SHA-256</li>
              <li>Controle de acesso granular baseado em papéis (RBAC)</li>
              <li>Criptografia de ponta a ponta em trânsito e repouso</li>
            </ul>
          </div>
        </div>
      </section>

      {/* 5. Comparativo Científico */}
      <section id="ciencia" className="landing-section landing-compare-section">
        <div className="landing-section-header">
          <span className="landing-section-tag">Benchmark de Mercado</span>
          <h2 className="landing-section-title">Por que as Organizações Escolhem o Metastatistic?</h2>
          <p className="landing-section-desc">
            Compare o poder de uma solução web moderna frente a ferramentas analíticas fragmentadas.
          </p>
        </div>

        <div className="landing-table-responsive card" style={{ padding: 0 }}>
          <table className="landing-compare-table">
            <thead>
              <tr>
                <th className="feature-col">Critério Analítico</th>
                <th>BI Tradicional <br /><span className="muted small">(Power BI / Tableau / Metabase)</span></th>
                <th>Softwares Desktop <br /><span className="muted small">(SPSS / JASP / RStudio)</span></th>
                <th className="highlight-col">Metastatistic Commercial <br /><span className="landing-badge-brand">Unificado Cloud</span></th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="feature-col">Preparação de Dados sem Código (Visual Prep)</td>
                <td><span className="status-yes">✓</span> Completo</td>
                <td><span className="status-partial">~</span> Manual / Rígido</td>
                <td className="highlight-col"><span className="status-yes">✓</span> DuckDB & Arrow em Memória</td>
              </tr>
              <tr>
                <td className="feature-col">Rigor Estatístico Frequentista & Bayesiano</td>
                <td><span className="status-no">✕</span> Apenas agregações básicas</td>
                <td><span className="status-yes">✓</span> Completo</td>
                <td className="highlight-col"><span className="status-yes">✓</span> Completo (R Worker Engine)</td>
              </tr>
              <tr>
                <td className="feature-col">Formatação Estrita APA 7th (Tabelas & Narrativa)</td>
                <td><span className="status-no">✕</span> Não disponível</td>
                <td><span className="status-partial">~</span> Apenas JASP (Desktop)</td>
                <td className="highlight-col"><span className="status-yes">✓</span> Nativo, com 1 clique</td>
              </tr>
              <tr>
                <td className="feature-col">Colaboração Web & Dashboards em Tempo Real</td>
                <td><span className="status-yes">✓</span> Sim</td>
                <td><span className="status-no">✕</span> Ficheiros locais (.jasp, .sav)</td>
                <td className="highlight-col"><span className="status-yes">✓</span> Cloud Colaborativo Nativo</td>
              </tr>
              <tr>
                <td className="feature-col">Governança, SSO SAML & SCIM 2.0</td>
                <td><span className="status-yes">✓</span> Disponível em Enterprise</td>
                <td><span className="status-no">✕</span> Inexistente em desktop</td>
                <td className="highlight-col"><span className="status-yes">✓</span> Okta, Entra ID, PingIdentity</td>
              </tr>
              <tr>
                <td className="feature-col">Trilha de Auditoria Imutável (FDA 21 CFR Part 11)</td>
                <td><span className="status-no">✕</span> Logs básicos</td>
                <td><span className="status-no">✕</span> Inexistente</td>
                <td className="highlight-col"><span className="status-yes">✓</span> Hash-chaining SHA-256</td>
              </tr>
              <tr>
                <td className="feature-col">Exportação de Relatórios Multi-Formato</td>
                <td><span className="status-partial">~</span> PDF / Imagem</td>
                <td><span className="status-partial">~</span> HTML / PDF básico</td>
                <td className="highlight-col"><span className="status-yes">✓</span> PDF A4, Word DOCX, LaTeX, MD</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* 6. Segurança e Conformidade Regulatória */}
      <section id="seguranca" className="landing-section">
        <div className="landing-section-header">
          <span className="landing-section-tag">Conformidade & Governança</span>
          <h2 className="landing-section-title">Projetado para os Ambientes Mais Críticos do Mundo</h2>
          <p className="landing-section-desc">
            Atendemos aos requisitos de segurança cibernética e soberania de dados exigidos por instituições hospitalares,
            centros de pesquisa clínica e empresas listadas em bolsa.
          </p>
        </div>

        <div className="landing-compliance-grid">
          <div className="landing-compliance-item card">
            <div className="landing-compliance-badge">FDA 21 CFR Part 11</div>
            <h4>Integridade Farmacêutica e Clínica</h4>
            <p>
              Trilhas de auditoria à prova de adulteração com encadeamento de hash criptográfico SHA-256.
              Cada alteração de dataset, execução de teste e compartilhamento de relatório é gravada imutavelmente com timestamp ISO UTC e identificação do operador.
            </p>
          </div>

          <div className="landing-compliance-item card">
            <div className="landing-compliance-badge">SOC 2 Type II Ready</div>
            <h4>Segurança e Alta Disponibilidade</h4>
            <p>
              Práticas operacionais alinhadas aos Trust Services Criteria.
              Isolamento lógico estrito entre organizações (multi-tenancy seguro), criptografia AES-256 em repouso e TLS 1.3 em todas as comunicações de rede.
            </p>
          </div>

          <div className="landing-compliance-item card">
            <div className="landing-compliance-badge">SSO & SCIM 2.0</div>
            <h4>Federação de Identidades</h4>
            <p>
              Integração com Microsoft Entra ID (Azure AD), Okta, Google Workspace e provedores compatíveis com SAML 2.0 e OpenID Connect.
              Sincronização automática de usuários e grupos via protocolo SCIM 2.0.
            </p>
          </div>

          <div className="landing-compliance-item card">
            <div className="landing-compliance-badge">Soberania de Dados</div>
            <h4>LGPD, GDPR & HIPAA</h4>
            <p>
              Total controle sobre o ciclo de vida dos dados científicos.
              Suporte a implantação em nuvem privada dedicada (VPC) ou On-Premises para conformidade irrestrita com regulamentações de sigilo de pacientes.
            </p>
          </div>
        </div>
      </section>

      {/* 7. Planos e Preços */}
      <section id="planos" className="landing-section">
        <div className="landing-section-header">
          <span className="landing-section-tag">Preços Transparentes</span>
          <h2 className="landing-section-title">Escolha o Plano Ideal para a sua Equipe</h2>
          <p className="landing-section-desc">
            Comece gratuitamente sem cartão de crédito e faça upgrade conforme o crescimento da sua demanda estatística.
          </p>

          <div className="landing-cycle-toggle">
            <button
              type="button"
              className={`landing-cycle-btn ${pricingPeriod === "monthly" ? "active" : ""}`}
              onClick={() => setPricingPeriod("monthly")}
            >
              Faturamento Mensal
            </button>
            <button
              type="button"
              className={`landing-cycle-btn ${pricingPeriod === "yearly" ? "active" : ""}`}
              onClick={() => setPricingPeriod("yearly")}
            >
              Faturamento Anual <span className="landing-discount-chip">2 Meses Grátis</span>
            </button>
          </div>
        </div>

        <div className="landing-pricing-grid">
          {/* Card Community */}
          <div className="landing-pricing-card card">
            <div className="landing-pricing-tier">Community</div>
            <div className="landing-pricing-cost">
              <span className="landing-amount">$0</span>
              <span className="landing-period">/ para sempre</span>
            </div>
            <p className="landing-pricing-desc">
              Ideal para pesquisadores individuais, estudantes e pequenas equipes acadêmicas.
            </p>
            <button
              type="button"
              className="btn landing-plan-btn"
              onClick={() => onOpenAuth("register")}
            >
              Criar Conta Gratuita
            </button>
            <div className="landing-pricing-features">
              <strong>Recursos incluídos:</strong>
              <ul>
                <li>✓ Até 3 usuários na organização</li>
                <li>✓ Até 10 datasets armazenados</li>
                <li>✓ 500 MB de armazenamento em nuvem</li>
                <li>✓ Análise estatística completa (R Worker Engine)</li>
                <li>✓ Dashboards e relatórios fundamentais</li>
                <li>✓ Exportação em HTML e Markdown</li>
              </ul>
            </div>
          </div>

          {/* Card Team */}
          <div className="landing-pricing-card card featured">
            <div className="landing-popular-badge">Mais Popular</div>
            <div className="landing-pricing-tier">Team</div>
            <div className="landing-pricing-cost">
              <span className="landing-amount">
                {pricingPeriod === "yearly" ? "$40" : "$49"}
              </span>
              <span className="landing-period">/ mês {pricingPeriod === "yearly" ? "(cobrado anualmente)" : ""}</span>
            </div>
            <p className="landing-pricing-desc">
              Para laboratórios de pesquisa, clínicas, universidades e equipes analíticas corporativas.
            </p>
            <button
              type="button"
              className="btn primary landing-plan-btn"
              onClick={() => onOpenAuth("register")}
            >
              Iniciar Teste Gratuito
            </button>
            <div className="landing-pricing-features">
              <strong>Tudo do Community mais:</strong>
              <ul>
                <li>✓ Até 15 usuários ativos</li>
                <li>✓ Até 100 datasets simultâneos</li>
                <li>✓ 10 GB de armazenamento ultrarrápido</li>
                <li>✓ Conectores SQL nativos (Postgres, MySQL, Snowflake)</li>
                <li>✓ Compartilhamento de coleções e workspaces</li>
                <li>✓ Exportação multi-formato (PDF A4, Word DOCX)</li>
                <li>✓ Suporte técnico prioritário por e-mail</li>
              </ul>
            </div>
          </div>

          {/* Card Enterprise */}
          <div className="landing-pricing-card card">
            <div className="landing-enterprise-badge">Corporativo & Regulatório</div>
            <div className="landing-pricing-tier">Enterprise</div>
            <div className="landing-pricing-cost">
              <span className="landing-amount">
                {pricingPeriod === "yearly" ? "$249" : "$299"}
              </span>
              <span className="landing-period">/ mês {pricingPeriod === "yearly" ? "(cobrado anualmente)" : ""}</span>
            </div>
            <p className="landing-pricing-desc">
              Para hospitais, CROs farmacêuticas, instituições financeiras e grandes corporações.
            </p>
            <button
              type="button"
              className="btn landing-plan-btn"
              onClick={() => onOpenAuth("register")}
            >
              Falar com Especialistas
            </button>
            <div className="landing-pricing-features">
              <strong>Tudo do Team mais:</strong>
              <ul>
                <li>✓ Usuários e datasets ilimitados</li>
                <li>✓ Armazenamento corporativo sem limites</li>
                <li>✓ Single Sign-On (SSO SAML 2.0 / OIDC)</li>
                <li>✓ Provisionamento SCIM 2.0 automático</li>
                <li>✓ Trilha de auditoria imutável (FDA 21 CFR Part 11)</li>
                <li>✓ Engine B de alta performance (&gt;100k linhas)</li>
                <li>✓ SLA de 99.9% e suporte 24/7 com gerente dedicado</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* 8. Call to Action Pré-Footer */}
      <section className="landing-cta-banner card">
        <div className="landing-cta-content">
          <h2>Pronto para elevar o nível da sua análise de dados?</h2>
          <p>
            Junte-se a cientistas, bioestatísticos e analistas que já transformaram seus fluxos de trabalho com o rigor do Metastatistic.
          </p>
          <div className="landing-hero-cta" style={{ justifyContent: "center", marginTop: 18 }}>
            <button
              type="button"
              className="btn primary lg"
              onClick={() => onOpenAuth("register")}
            >
              Criar Conta Gratuita Agora
            </button>
            <button
              type="button"
              className="btn lg"
              onClick={() => onOpenAuth("login")}
            >
              Acessar Minha Conta
            </button>
          </div>
        </div>
      </section>

      {/* 9. Footer Institucional */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="landing-footer-brand">
            <div className="landing-brand">
              <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
                <rect x="5" y="15" width="5" height="12" rx="1.5" fill="var(--series-1)" />
                <rect x="13.5" y="7" width="5" height="20" rx="1.5" fill="var(--series-2)" />
                <rect x="22" y="11" width="5" height="16" rx="1.5" fill="var(--series-3)" />
              </svg>
              <span className="landing-brand-name">Metastatistic</span>
            </div>
            <p className="landing-footer-tagline">
              A convergência definitiva entre o poder visual do BI corporativo e o rigor científico da estatística inferencial.
            </p>
            <div className="landing-footer-seals">
              <span className="landing-seal">APA 7th Standard</span>
              <span className="landing-seal">FDA 21 CFR Part 11</span>
              <span className="landing-seal">SOC 2 Ready</span>
              <span className="landing-seal">DuckDB & Arrow</span>
            </div>
          </div>

          <div className="landing-footer-links">
            <div className="landing-footer-col">
              <h5>Navegação</h5>
              <a href="#recursos">Recursos da Plataforma</a>
              <a href="#ciencia">Rigor Científico</a>
              <a href="#seguranca">Governança & Segurança</a>
              <a href="#planos">Planos e Preços</a>
            </div>

            <div className="landing-footer-col">
              <h5>Conectores & Análises</h5>
              <span>Testes t e Mann-Whitney</span>
              <span>ANOVA, ANCOVA & Welch</span>
              <span>Regressão Frequentista & Bayes</span>
              <span>DuckDB In-Memory Engine</span>
            </div>

            <div className="landing-footer-col">
              <h5>Acesso Rápido</h5>
              <button
                type="button"
                className="btn-link"
                style={{ textAlign: "left", padding: 0 }}
                onClick={() => onOpenAuth("login")}
              >
                Entrar na Conta
              </button>
              <button
                type="button"
                className="btn-link"
                style={{ textAlign: "left", padding: 0 }}
                onClick={() => onOpenAuth("register")}
              >
                Cadastre-se Gratuitamente
              </button>
            </div>
          </div>
        </div>

        <div className="landing-footer-bottom">
          <p>© {new Date().getFullYear()} Metastatistic Commercial. Todos os direitos reservados.</p>
          <p className="muted small">
            Desenvolvido para ambientes de pesquisa clínica, epidemiologia, bioestatística e tomada de decisão orientada por dados de alta integridade.
          </p>
        </div>
      </footer>
    </div>
  );
}
