# Metastatistic Commercial (Enterprise & Microservices)

Plataforma corporativa e B2B SaaS de Business Intelligence, Data Preparation e Rigor Estatístico Avançado (Frequentista e Bayesiano), unificando a agilidade visual e conectividade do [Metabase](https://github.com/metabase/metabase) com o rigor científico e relatórios em padrão APA 7th do [JASP](https://github.com/jasp-stats/jasp-desktop).

Consulte o documento mestre de arquitetura: **[PLAN.md](PLAN.md)**.

---

## 🏛️ Topologia e Estrutura do Monorepo

O repositório está organizado como um monorepo (`pnpm-workspace.yaml`):

### Microsserviços e Backend
- **`services/gateway`** (porta `8080`): API Gateway e Edge Router assíncrono com resolução de inquilinos em cascata (subdomínio, cabeçalho `X-Tenant-ID`, JWT Bearer), proxy streaming via `httpx` e healthcheck agregador.
- **`services/auth-tenant-service`** (porta `8002`): IAM, governança de inquilinos (*tenants*), cotas estritas por assinatura (`community`, `team`, `enterprise`), RBAC com proteção ao *owner*, convites criptografados, SSO SAML 2.0 / OIDC, SCIM 2.0 e Trilha de Auditoria Imutável (SHA-256 Hash Chain).
- **`services/stat-orchestrator`** (porta `8003`): Orquestrador de computação analítica com fila assíncrona priorizada por QoS (clientes VIP furam fila), cache determinístico LRU por hash SHA-256 e roteador inteligente Dual-Engine.
- **`services/data-engine-service`** (porta `8004` / exposta `8014`): Motor de consulta analítica em DuckDB Sandbox confinada, streaming binário Apache Arrow IPC (`application/vnd.apache.arrow.stream`), anonimização e mascaramento de PII (LGPD/GDPR), conectores externos (SQLite, DuckDB, PostgreSQL, MySQL) e Data Prep.
- **`services/bi-report-service`** (porta `8005` / exposta `8015`): Microsserviço de relatórios colaborativos e dashboards em tempo real com WebSockets, versionamento e snapshots.
- **`services/export-service`** (porta `8006` / exposta `8016`): Gerador de relatórios multi-formato (HTML/PDF Paged Media APA 7th, LaTeX com booktabs, DOCX com estilos acadêmicos e Markdown GFM).
- **`services/billing-service`** (porta `8007` / exposta `8017`): Microsserviço de monetização e pagamentos Stripe: planos Community, Team e Enterprise, Checkout Sessions, Customer Portal, faturamento multi-tenant e webhooks com atualização automática de tier.
- **`apps/api`** (porta `8000`): Camada de dados, ingestão de CSV/Parquet via DuckDB, catálogo de datasets, relatórios, dashboards e abstração de storage (`StorageProvider` Local/S3).
- **`engines/r-worker`**: **Engine A (Open Engine)** — Worker R isolado em container com supervisor leve e runtime JASP (tempo limite, recuperação automática, AGPL-compliant).

### Pacotes Compartilhados e Frontend
- **`packages/contracts`**: Contratos canônicos e interfaces TypeScript para entidades multi-tenant, tabelas APA 7th, especificações analíticas e metadados de armazenamento.
- **`packages/react-embed`**: Componente React seguro (`@metastatistic/react-embed`) para incorporação de relatórios, dashboards, gráficos e tabelas APA em aplicações externas via iframe com sandbox e comunicação bidirecional via `postMessage`.
- **`apps/web`**: Aplicação frontend (Vite + React 19 + TypeScript + ECharts) com suporte a análise estatística, construtor de dashboards interativos, editor de relatórios em blocos e visualizações com tema escuro/claro.

---

## 🚀 Fases Comerciais (Enterprise Roadmap)

O progresso da evolução corporativa está documentado minuciosamente nas notas de entrega abaixo:

- **[Fase Comercial 1 — Monorepo, Contratos, Armazenamento e Multi-Tenancy ✅](docs/commercial-phase1-progress.md)**:
  - Setup do monorepo e criação do pacote `@metastatistic/contracts`.
  - Abstração agnóstica de armazenamento de arquivos (`StorageProvider`) com provedores Local e Amazon S3/MinIO com cache local.
  - Multi-tenancy no banco de dados com auto-seed do tenant `default` e migração automática e retrocompatível de tabelas principais.
- **[Fase Comercial 2 — IAM, Multi-Tenancy e API Gateway ✅](docs/commercial-phase2-progress.md)**:
  - Microsserviço `auth-tenant-service` com cotas por plano, convites e tokens JWT.
  - Microsserviço `gateway` com resolução de inquilinos em cascata (subdomínio, cabeçalho, JWT), proxy reverso assíncrono e healthcheck agregador unificado.
  - Orquestração distribuída via `docker-compose.microservices.yml`.
- **[Fase Comercial 3 — Microsserviço de Consulta, Conectores e Data Prep ✅](docs/commercial-phase3-progress.md)**:
  - Microsserviço `data-engine-service` com DuckDB sandbox e validação AST via SQLGlot.
  - Streaming binário Apache Arrow IPC de alta velocidade (`application/vnd.apache.arrow.stream`).
  - Motor de mascaramento de PII (email, CPF, telefone, redaction e SHA-256 com salt isolado por tenant).
  - Conectores externos (SQLite, DuckDB, PostgreSQL, MySQL) e engine de preview de transformações.
  - Roteamento e healthcheck integrados no Gateway e orquestração Docker Compose.
- **[Fase Comercial 4 — Orquestrador Estatístico e Engine B (Pure Python) ✅](docs/commercial-phase4-progress.md)**:
  - Microsserviço `stat-orchestrator` com fila assíncrona, priorização VIP para planos Enterprise e cache determinístico LRU.
  - **Engine B comercial**: Cálculos estatísticos em Python puro/SciPy (100% livre de AGPL) para Descritivas, Testes t (Independente e Uma Amostra), ANOVA One-Way e Correlação de Pearson, com formatação estrita de tabelas e notas APA 7th.
  - Roteador Dual-Engine ('auto', 'py', 'r') garantindo conformidade e proteção de propriedade intelectual.
- **[Fase Comercial 5 — Microsserviço de Relatórios, BI e Exportação ✅](docs/commercial-phase5-progress.md)**:
  - Microsserviço `bi-report-service` com controle otimista de versão (conflito 409), histórico de snapshots com restauração instantânea, dashboards com tiles flexíveis e WebSockets para colaboração em tempo real.
  - Microsserviço `export-service` com exportação multi-formato: HTML/PDF com CSS Paged Media (`@page { size: A4; margin: 2.5cm; }`), LaTeX com `booktabs` e `amsmath`, DOCX formatado via `python-docx` e Markdown GFM.
  - Pacote `@metastatistic/react-embed` com `iframe` sandbox, postMessage bidirecional e `autoResize`.
  - Integração total com o API Gateway (`gateway`) e orquestração Docker Compose.
- **[Fase Comercial 6 — Prontidão Enterprise, Segurança Criptográfica e Orquestração Kubernetes ✅](docs/commercial-phase6-progress.md)**:
  - **SSO Corporativo (SAML 2.0 & OIDC)** com provisionamento Just-In-Time (JIT) e mapeamento de atributos para Okta, Azure AD, Google e Keycloak.
  - **Provisionamento SCIM 2.0** (RFC 7643 e RFC 7644) completo: `ServiceProviderConfig`, `Schemas`, `Users` com filtro, criação, desativação instantânea (`active: false`) e remoção.
  - **Trilha de Auditoria Criptográfica Imutável** (Merkle / SHA-256 Hash Chain) para conformidade estrita com SOC 2 Tipo II e FDA 21 CFR Part 11 com detecção matemática de adulteração em tempo real.
  - **API Gateway atualizado** com roteamento transparente para `/api/v1/sso/*`, `/scim/v2/*` e `/api/v1/audit/*`.
  - **Helm Charts Oficiais Kubernetes Enterprise** (`deploy/helm/metastatistic`) com HPA, Ingress TLS, ConfigMap, Secrets e Deployments/Services para os 7 microsserviços.
- **[Fase Comercial 7 — Microsserviço de Billing e Monetização Stripe ✅](docs/commercial-billing-progress.md)**:
  - **Microsserviço `billing-service`** com planos Community ($0), Team ($49/mês) e Enterprise ($299/mês).
  - **Checkout Sessions & Customer Portal Stripe** com suporte a modo mock seguro para ambientes de desenvolvimento e CI/CD.
  - **Processamento de Webhooks Stripe** (`checkout.session.completed`, `customer.subscription.deleted`, `invoice.*`) com verificação criptográfica de assinatura e atualização automática de planos no `auth-tenant-service`.
  - **Isolamento multi-tenant** completo para histórico de faturas e assinaturas.
  - **Suporte completo no Gateway, Docker Compose e Helm Charts Kubernetes**.

---

## 🔬 Fases do Motor Estatístico Base (Histórico)

- **[Fase 8 — Transformações de Dados (Power Query web)](docs/phase8-progress.md)**: Passos encadeados em DuckDB com receitas salvas, colunas calculadas, agregações por janela e reshape (pivot/unpivot/join/append).
- **[Fase 7 — Governança e Permissões](docs/phase7-progress.md)**: Controle de acesso refinado por dataset, segurança por linha (Row-Level Security) e trilha de auditoria.
- **[Fase 6 — Catálogo Estatístico Expandido](docs/phase6-progress.md)**: 10 análises estatísticas validadas contra o R puro (testes t, ANOVA, ANCOVA, regressão linear/logística, qui-quadrado, descritivas).
- **[Fase 5 — Dashboards Interativos](docs/phase5-progress.md)**: Grade flexível, filtros dinâmicos globais (`{{param}}`), cross-filtering entre gráficos e tiles de análises inferenciais.
- **[Fase 4 — Análises Estatísticas Avançadas](docs/phase4-progress.md)**: Testes inferenciais multivariados com relatórios em estilo APA.
- **[Fase 3 — Editor de Relatórios](docs/phase3-progress.md)**: Documentos com blocos de texto, gráficos e análises com exportação em PDF.
- **[Fase 2 — Execução Robusta de Análises](docs/phase2-progress.md)**: Pool de workers R resilientes com supervisor de processo e timeout.
- **[Fase 1 — Camada de Dados e Ingestão](docs/phase1-progress.md)**: Ingestão de CSV para Apache Parquet via DuckDB e consultas analíticas seguras.
- **[Fase 0 — Spike de Arquitetura e Descobertas](docs/phase0-findings.md)**: Prova de conceito e neutralização de armadilhas iniciais.

---

## 🛠️ Como Executar

### 1. Orquestração Completa de Microsserviços (Docker Compose)
Para subir o ecossistema distribuído de microsserviços:
```bash
docker compose -f docker-compose.microservices.yml up -d --build
```
Serviços disponíveis:
- **API Gateway**: `http://localhost:8080` (Healthcheck unificado em `http://localhost:8080/health`)
- **Frontend Web**: `http://localhost:8080`
- **Auth & Tenant Service**: `http://localhost:8002`
- **Stat Orchestrator**: `http://localhost:8003`
- **Data Engine Service**: `http://localhost:8014` (porta interna `8004`)
- **BI Report Service**: `http://localhost:8015` (porta interna `8005`)
- **Export Service**: `http://localhost:8016` (porta interna `8006`)
- **Billing Service**: `http://localhost:8017` (porta interna `8007`)
- **Data API**: `http://localhost:8000`

### 2. Execução dos Testes Automatizados

#### Microsserviços e Backend Python
```bash
# Testes do Billing Service (9 testes)
uv run --directory services/billing-service pytest

# Testes do BI Report Service (6 testes)
uv run --directory services/bi-report-service pytest

# Testes do Export Service (6 testes)
uv run --directory services/export-service pytest

# Testes do Data Engine Service (10 testes)
uv run --directory services/data-engine-service pytest

# Testes do Stat Orchestrator (13 testes)
uv run --directory services/stat-orchestrator pytest

# Testes do Auth Tenant Service (12 testes incluindo SSO, SCIM, Auditoria e Atualização de Tier)
uv run --directory services/auth-tenant-service pytest

# Testes do API Gateway (11 testes incluindo rotas Enterprise e Billing)
uv run --directory services/gateway pytest

# Testes da API de Dados (330 testes)
uv run --directory apps/api pytest
```

#### Pacotes e Frontend (TypeScript / React)
```bash
# Testes do pacote React Embed
pnpm --filter @metastatistic/react-embed test

# Testes unitários do frontend (259 testes)
pnpm --filter web test --run

# Validação de tipos e build do monorepo
pnpm -r run build
```
