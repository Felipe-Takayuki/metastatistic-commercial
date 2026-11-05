# Plano de Implementação — Metastatistic

Plataforma web de relatórios estatísticos que sintetiza as principais funcionalidades do [JASP](https://github.com/jasp-stats/jasp-desktop) e do [Metabase](https://github.com/metabase/metabase).

## 1. Visão do produto

O que cada ferramenta contribui:

| Vem do **Metabase** | Vem do **JASP** | Fica na interseção (o diferencial) |
|---|---|---|
| Conexão com bancos (Postgres, MySQL, BigQuery…) | Análises estatísticas por formulário, sem código | **Relatórios** que misturam texto, gráficos de BI e análises estatísticas |
| Query builder visual e editor SQL | Abordagens frequentista e bayesiana | Filtros do relatório que reexecutam gráficos **e** análises |
| Dashboards, filtros e cross-filter | Tabelas em formato APA | Interpretação automática dos resultados (opcional, com IA) |
| Coleções, permissões, agendamento e embed | Gráficos estatísticos (QQ-plot, resíduos, posteriores) | Resultados reprodutíveis e versionados |

## 2. Decisões estratégicas (tomar antes de codar)

**Licença.** JASP e Metabase são AGPL-3.0. Se você copiar código de qualquer um, a plataforma inteira precisa ser AGPL, e isso vale também para SaaS. Há dois caminhos:

- **A (recomendado):** reaproveitar os **módulos R do JASP** (`jaspDescriptives`, `jaspTTests`, `jaspAnova`, `jaspRegression` etc.) como motor estatístico num serviço separado, e escrever a parte de BI do zero, só com os *conceitos* do Metabase. Isso dá ganho enorme de tempo e validação estatística, mas implica aceitar a AGPL ou isolar bem o serviço e consultar um advogado.
- **B:** motor estatístico próprio em Python (scipy, statsmodels, pingouin, PyMC/bambi). Você fica livre para escolher a licença, mas leva bem mais tempo para chegar à paridade com o JASP.

> **Decisão (2026-11-04):** o usuário confirmou o **caminho A** — motor estatístico com módulos R reais do JASP; parte de BI escrita do zero (só conceitos do Metabase, nenhum código copiado). Escopo de BI limitado ao que o relatório precisa (CSV, SQL, gráficos, análises); drivers de banco e permissões pesadas ficam para depois.

**Motor estatístico.** O pacote `jaspTools` roda as análises do JASP direto em R, sem a interface desktop: você passa um dataset e uma lista de opções e recebe a saída do `jaspResults` (tabelas e gráficos). É isso que torna o caminho A viável.

## 3. Arquitetura proposta

```
┌────────────── Frontend (React + TypeScript, Vite/Next.js) ──────────────┐
│ Editor de relatório (TipTap/ProseMirror, blocos)  │ Dashboards (grid)  │
│ Query builder + editor SQL (Monaco)               │ Gráficos: ECharts  │
│ Formulários de análise gerados por JSON Schema    │ UI: shadcn/Tailwind│
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ REST/WebSocket
┌──────────────────────────────▼──────────────────────────────────────────┐
│ API (Python FastAPI)                                                    │
│ auth/RBAC · metadados · query engine (SQLGlot → SQL do dialeto)         │
│ cache de resultados · agendamentos · exportação PDF (Playwright)       │
└───────┬───────────────────┬──────────────────────┬──────────────────────┘
        │                   │ fila (Redis)         │
┌───────▼───────┐   ┌───────▼────────────┐   ┌─────▼─────────────────────┐
│ Postgres      │   │ Workers R          │   │ Fontes de dados           │
│ (app DB)      │   │ jaspTools + módulos│   │ Postgres/MySQL/BigQuery/  │
│ MinIO/S3      │   │ dados via Arrow    │   │ CSV/Excel → DuckDB        │
└───────────────┘   └────────────────────┘   └───────────────────────────┘
```

Pontos principais:

- **DuckDB** guarda os uploads (CSV, Excel, SPSS `.sav` via `pyreadstat`) e serve de camada analítica rápida.
- **Os dados vão para o R via Apache Arrow**, sem CSV no meio. Cada worker roda num container isolado, com timeout e limite de memória.
- **Dois tipos de gráfico:**
  - Gráficos de BI interativos no cliente, com ECharts.
  - Gráficos estatísticos gerados no servidor pelo `jaspGraphs`/ggplot2 em SVG. Os mais usados podem migrar depois para ECharts interativo.
- **Reprodutibilidade:** cada resultado guarda o hash dos dados, as opções e as versões dos pacotes (fixadas com `renv`).

## 4. Modelo de domínio

- `DataSource`: uma conexão ou um upload.
- `Dataset/Model`: camada semântica com tipos das colunas, nível de medida (nominal, ordinal, escalar, como no JASP) e rótulos.
- `Question`: uma query (visual ou SQL) mais a visualização.
- `Analysis`: o tipo de análise, as opções (JSON), uma referência ao dataset e o resultado em cache.
- `Report`: uma lista ordenada de blocos (texto, question, analysis, filtro, KPI), com versionamento.
- `Dashboard`, `Collection`, `Permission`, `Schedule`, `Subscription`.

## 5. Fases

### Fase 0: Fundação (2 semanas)

- Monorepo (`apps/web`, `apps/api`, `engines/r-worker`, `packages/schemas`), Docker Compose e CI.
- Prova de conceito (spike): rodar `jaspTools::runAnalysis` para um teste t dentro de um container e mapear o JSON de saída do `jaspResults`.
- Definir a licença e o design system.

### Fase 1: Camada de dados, o "mini-Metabase" (5–6 semanas)

- Upload de CSV/Excel e conexão com Postgres/MySQL.
- Navegador de schema e editor SQL com autocomplete.
- Query builder visual: filtro, agrupar, agregar, ordenar, join simples.
- Visualizações básicas: tabela, barra, linha, área, pizza, dispersão, KPI e mapa de calor.
- Segurança: usuário somente leitura no banco, timeout e limite de linhas por query.

### Fase 2: Motor estatístico, o "JASP web" (6–8 semanas)

- Fila de jobs, workers R, progresso via WebSocket e cache.
- Formulários: converter os QML dos módulos JASP em **JSON Schema** e renderizar com um gerador de formulários, mantendo os nomes de opções que o R espera.
- Primeiro lote de análises:
  - Descritivas e frequências.
  - Testes t (independente, pareado, uma amostra).
  - ANOVA e ANCOVA (com post-hoc).
  - Correlação.
  - Regressão linear e logística.
  - Tabelas de contingência (qui-quadrado).
  - As versões **bayesianas** desses testes.
- Renderizador de tabelas APA: notas de rodapé, sobrescritos e formatação numérica.
- Verificação automática de pressupostos (normalidade, homogeneidade), com avisos na própria saída.

### Fase 3: Relatórios, o coração do produto (5–6 semanas)

- Editor em blocos: texto rico, question, análise, KPI e divisor de seção.
- **Parâmetros globais do relatório**: um filtro de data ou segmento reexecuta queries e análises.
- Templates de relatório e temas visuais (paleta, tipografia, logo).
- Exportação em PDF (Chromium headless) e DOCX; link público com token.
- Histórico de versões e comentários.

### Fase 4: Dashboards e colaboração (4–5 semanas)

- Grid arrastável (react-grid-layout), cross-filter e drill-down.
- Coleções, RBAC (admin, editor, viewer) e permissões por fonte de dados.
- Segurança por linha (*row-level security*) via atributos do usuário.

### Fase 5: Automação e enterprise (4–6 semanas)

- Envio agendado de relatórios por e-mail e Slack, e alertas por limiar.
- Embed via JWT assinado (como o *static embedding* do Metabase).
- SSO (OIDC/SAML), log de auditoria, cache por fonte e observabilidade (OpenTelemetry).

### Fase 6: Avançado (contínuo)

- Mais módulos JASP: análise fatorial e PCA, SEM (lavaan), confiabilidade, meta-análise, machine learning, séries temporais.
- **Assistente com IA**: pergunta em linguagem natural vira query ou análise, com interpretação textual dos resultados em estilo APA.

**Estimativa:** um MVP útil (Fases 0–3) leva de 4 a 5 meses com uma equipe de 3–4 pessoas: frontend sênior, backend Python, pessoa de estatística/R, e DevOps em meio período.

## 6. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Acoplamento ao formato interno do `jaspResults` | Camada adaptadora que converte para um schema próprio (`packages/schemas`) |
| R é lento para subir e escala mal | Pool de workers aquecidos e cache por hash de dados + opções |
| Datasets grandes: estatística precisa de linhas, não de agregados | Limite configurável, amostragem explícita com aviso e, quando der, agregação no próprio banco |
| Paridade com os formulários QML do JASP | Converter só as análises priorizadas e testar contra as saídas do JASP desktop (testes golden) |
| SQL arbitrário contra bancos de produção | Credenciais somente leitura, timeout, `LIMIT` forçado e auditoria |

## 7. Critério de sucesso do MVP

Um usuário sobe um CSV ou conecta um Postgres e monta um gráfico de vendas por região. No mesmo relatório, roda uma ANOVA bayesiana comparando as regiões. Depois aplica um filtro de período que atualiza tudo e exporta um PDF com visual profissional.

## 8. Próximo passo

Começar pela prova de conceito da Fase 0: worker R rodando um teste t via `jaspTools` dentro de um container, chamado pela API FastAPI. Ela valida a decisão mais arriscada do plano.
