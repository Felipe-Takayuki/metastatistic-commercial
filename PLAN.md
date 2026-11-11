# Plano de Arquitetura e Implementação — Metastatistic Commercial (Enterprise & Microservices)

Plataforma unificada corporativa e B2B SaaS de Business Intelligence, Data Preparation e Rigor Estatístico Avançado (Frequentista e Bayesiano), combinando o melhor do [JASP](https://github.com/jasp-stats/jasp-desktop) e do [Metabase](https://github.com/metabase/metabase).

---

## 0. Estado Atual (2026-11-11)

Este documento é o **plano**; a tabela abaixo diz o que **existe hoje** no repositório. O diagrama da §3 e as tecnologias citadas na §3.1 (Traefik/Envoy, PostgreSQL, Redis, RabbitMQ, S3) são a **arquitetura-alvo**: na implementação atual cada serviço é FastAPI com SQLite próprio e um gateway FastAPI sob medida (ver §7).

| Plano (§3.1) | Implementado em | Status |
|---|---|---|
| 1. API Gateway | `services/gateway` | ✅ proxy por prefixo, tenant em cascata, `/health` agregado. Sem TLS próprio |
| 2. Auth & Multi-Tenancy | `services/auth-tenant-service` | ✅ tenants, RBAC, convites, JWT, SSO SAML/OIDC, SCIM 2.0. Sem *Workspaces* |
| 3. Billing | `services/billing-service` | ✅ Stripe (modo mock em dev). ⬜ medição de uso |
| 4. Data Engine | `services/data-engine-service` | ✅ DuckDB sandbox, Arrow IPC, PII, conectores |
| 5. Stat Orchestrator | `services/stat-orchestrator` | ✅ fila por QoS, cache LRU, Dual-Engine. Fila em memória (sem Redis/RabbitMQ) |
| 6. Workers | `engines/r-worker` (Engine A) + Engine B dentro do orquestrador | ✅ / ⬜ não há cluster de workers Python separado |
| 7. BI & Reports | `services/bi-report-service` | ✅ |
| 8. Export | `services/export-service` | ✅ |
| 9. Frontend | `apps/web` (+ `packages/react-embed`) | ✅ |
| 10. Audit Trail | `services/audit-service` | ✅ extraído do auth em 2026-11-11 (Fase 8) |
| (monólito original) | `apps/api` | ✅ datasets, relatórios, dashboards, usuários; mantém um log de auditoria próprio (§7) |

---

## 1. Visão Executiva e Posicionamento de Mercado

### 1.1 Transformação do Produto: Do Monólito Experimental ao Enterprise SaaS
O **Metastatistic Commercial** nasce da necessidade de transicionar um protótipo de análise local/monolítica para uma infraestrutura distribuída, altamente escalável, multi-inquilino (*multi-tenant*), segura e pronta para monetização comercial.

A proposta de valor central é eliminar o abismo existente entre ferramentas de **Business Intelligence corporativo** (rápidas, visuais, voltadas a métricas simples e dashboards operacionais) e softwares de **análise estatística especializada** (pesados, desktop-bound, focados em pesquisa acadêmica e inferência rigorosa).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            METANASTATISTIC COMMERCIAL                        │
│                                                                              │
│    AGILIDADE E CONECTIVIDADE BI                 RIGOR E CIÊNCIA ESTATÍSTICA  │
│         (DNA Metabase)                               (DNA JASP)              │
│  - Conectores SQL heterogêneos             - Formato de publicação APA 7th   │
│  - Query Builder visual (sem código)        - Inferência Frequentista & Bayes │
│  - Cross-filtering & Dashboards            - Diagnósticos (QQ-plot, Resíduos)│
│  - Governança, Metadados e Catálogo        - Relatórios reprodutíveis        │
│                                      ▲                                       │
│                                      │                                       │
│                     DIFERENCIAIS COMPETITIVOS ÚNICOS                         │
│   • Relatórios com Blocos Híbridos (Texto rico + BI interativo + Estatística)│
│   • Filtros Dinâmicos Globais que recalculam gráficos E testes inferenciais   │
│   • Interpretação Narrativa Automatizada de P-valor e Fatores de Bayes (BF) │
│   • SDK de Incorporação (@metastatistic/react-embed) para outros SaaS        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Casos de Uso Comerciais e Setores-Alvo
1. **Empresas de Pesquisa Clínica & Indústria Farmacêutica (CROs / Pharma)**:
   - Validação de ensaios clínicos, bioequivalência, testes A/B farmacológicos e relatórios auditáveis compatíveis com FDA 21 CFR Part 11 e boas práticas de laboratório (GxP).
2. **FinTechs, Risco, Crédito & Seguradoras**:
   - Modelagem de escores de crédito, análise de sobrevivência para default, testes de hipóteses de risco de mercado e relatórios de compliance para bancos centrais.
3. **Instituições de Ensino Superior, Centros de Pesquisa & Laboratórios**:
   - Plataforma em nuvem colaborativa para estudantes, docentes e pesquisadores substituindo licenças legadas individuais de SPSS/SAS por uma solução web moderna e colaborativa.
4. **Corporações & Escalas de Data Science / Product Analytics**:
   - Times de experimentação (growth, marketing, produto) conduzindo testes A/B/n bayesianos com dashboards executivos integrados ao data warehouse (Snowflake/BigQuery/Postgres).

---

## 2. Estratégia de Licenciamento, Compliance e Propriedade Intelectual (AGPL-3.0 vs Solução Proprietária)

### 2.1 O Desafio Jurídico do Copyleft AGPL
Tanto o código-fonte original do **JASP Desktop** quanto o **Metabase** utilizam a licença **GNU Affero General Public License v3 (AGPL-3.0)**. 
No modelo SaaS e em distribuições corporativas proprietárias (*On-Premise closed-source*), a AGPL impõe que qualquer modificação ou obra derivada disponibilizada pela rede tenha seu código-fonte integral aberto sob a mesma licença, representando risco de contaminação aos ativos intelectuais comerciais.

### 2.2 Arquitetura "Dual-Engine" e Isolamento de Rede

Para neutralizar esse risco e permitir uma oferta comercial híbrida (Open Core + Enterprise Fechado), o sistema adota uma fronteira estrita por arquitetura distribuída:

```
                  ┌─────────────────────────────────────────────────────────┐
                  │          Metastatistic Commercial Platform              │
                  │   (Proprietária / Enterprise / B2B SaaS Closed Source)  │
                  └────────────┬──────────────────────────────┬─────────────┘
                               │                              │
             Contrato IPC/gRPC │            Contrato Interno  │
               via Rede Aberta │             Python / Native  │
                               ▼                              ▼
    ┌──────────────────────────────────────┐     ┌──────────────────────────────┐
    │       ENGINE A (Open Engine)         │     │   ENGINE B (Enterprise Core) │
    │ ------------------------------------ │     │ ---------------------------- │
    │ • Licença: AGPL-3.0 / GPL Compliance │     │ • Licença: Proprietária      │
    │ • Runtimes: R + jaspTools            │     │ • Runtimes: Python / Rust    │
    │ • Módulos: jaspDescriptives,         │     │ • Stack: SciPy, Statsmodels, │
    │   jaspTTests, jaspAnova,             │     │   Pingouin, PyMC, Polars,    │
    │   jaspRegression, etc.               │     │   Apache Arrow Nativo        │
    │ • Comunicação: gRPC / Arrow IPC      │     │ • Ideal para: On-Premise,    │
    │ • Execução em Worker Containers      │     │   Air-Gapped, Finanças e     │
    │   100% isolados de rede pública      │     │   Clientes estritos sem AGPL │
    └──────────────────────────────────────┘     └──────────────────────────────┘
```

1. **Engine A (Open Engine - Módulos JASP R)**:
   - Opera como um microsserviço autônomo e desacoplado (`stat-worker-r`).
   - Comunica-se exclusivamente através de chamadas IPC/gRPC serializadas em Apache Arrow sobre sockets de rede.
   - Todo o código contido neste serviço é mantido em conformidade com a AGPL-3.0, mas não contamina os demais serviços da plataforma (Gateway, Auth, Billing, Data Engine e UI), que permanecem proprietários sob o princípio de agregação independente de rede (*independent network-separated services*).
2. **Engine B (Enterprise Engine - Pure Python / Rust / Julia)**:
   - Motor proprietário livre de código AGPL construído com bibliotecas licenciadas sob BSD, MIT e Apache 2.0 (SciPy, Statsmodels, Pingouin, Scikit-learn, PyMC, Polars, DuckDB).
   - Replica com precisão os algoritmos matemáticos e tabelas APA 7th.
   - Fornece garantia contratual de IP limpo (*indemnification*) para clientes corporativos de grande porte que proíbem qualquer componente AGPL em suas redes internas.

---

## 3. Topologia e Decomposição em Microsserviços

A plataforma adota arquitetura orientada a serviços (*Microservices & Event-Driven Architecture*), orquestrada em Kubernetes com contratos estritos baseados em OpenAPI v3 e Protocol Buffers / gRPC.

```mermaid
flowchart TD
    Client["Browser Web / Embedded SDK / Mobile"] -->|HTTPS / WSS| Gateway["1. API Gateway & Edge Router\n(Traefik / Envoy)"]

    subgraph Core_Services["Plataforma Central (Enterprise Services)"]
        Gateway --> Auth["2. Auth & Multi-Tenancy\n(auth-tenant-service)"]
        Gateway --> Billing["3. Billing & Metering\n(billing-service)"]
        Gateway --> DataEng["4. Data Engine & Query\n(data-engine-service)"]
        Gateway --> StatOrch["5. Stat Orchestrator\n(stat-orchestrator)"]
        Gateway --> BIReport["7. BI & Reports\n(bi-report-service)"]
        Gateway --> Export["8. Export & Delivery\n(export-service)"]
        Gateway --> Audit["9. Audit Trail\n(audit-service)"]
        Auth -.->|eventos de auditoria| Audit
    end

    subgraph Data_Storage["Camada de Dados & Mensageria"]
        Postgres[(PostgreSQL 16 Multi-tenant)]
        Redis[(Redis Cluster / Caching)]
        RabbitMQ[[RabbitMQ / Kafka Queue]]
        S3[(MinIO / S3 Object Storage)]
    end

    subgraph Workers["Cluster Elástico de Processamento"]
        StatOrch -->|Jobs assíncronos| RabbitMQ
        RabbitMQ --> WorkerR["6a. Stat Worker R\n(Engine A - JASP)"]
        RabbitMQ --> WorkerPy["6b. Stat Worker Python\n(Engine B - Proprietary)"]
    end

    Auth --> Postgres
    Billing --> Postgres
    DataEng --> Postgres
    BIReport --> Postgres
    BIReport --> S3
    Export --> S3
    Audit --> Postgres
    StatOrch --> Redis
    WorkerR --> S3
    WorkerPy --> S3
```

### 3.1 Detalhamento de Cada Microsserviço

#### 1. API Gateway & Edge Router (`services/gateway`)
- **Tecnologia**: Traefik Enterprise ou Envoy Proxy.
- **Responsabilidades**:
  - Roteamento inteligente baseado em subdomínios de inquilinos (`{org_slug}.metastatistic.com` e domínios personalizados).
  - Terminação TLS automática (Let's Encrypt / Cert-Manager).
  - Verificação prévia de JWT, validação de tokens de API corporativos e CORS dinâmico.
  - Rate limiting adaptativo segregado por tier de assinatura (ex: Free: 60 req/min, Enterprise: 5.000 req/min).
  - OpenTelemetry distributed tracing e correlação de `X-Correlation-ID`.

#### 2. Identity, Multi-Tenancy & Access Management (`services/auth-tenant-service`)
- **Tecnologia**: Go ou Python FastAPI com SQLAlchemy 2.0 / Pydantic.
- **Responsabilidades**:
  - Estrutura hierárquica multi-tenant: Organizações (*Tenants*), Espaços de Trabalho (*Workspaces*), Equipes e Usuários.
  - Single Sign-On (SSO) corporativo: Integração com SAML 2.0 e OIDC (Okta, Azure Active Directory, PingFederate, Google Workspace).
  - SCIM 2.0 (*System for Cross-domain Identity Management*) para provisionamento e desprovisionamento automatizado de usuários por equipes de TI.
  - Controle de Acesso Baseado em Papéis e Atributos (RBAC/ABAC):
    - `Owner`, `Org Admin`, `Workspace Admin`, `Data Engineer`, `Senior Statistician`, `Analyst`, `Viewer`.
  - Emite eventos de auditoria (`tenant.create`, `member.role_update`, `auth.token_issued`, `sso.*`, `scim.*`…) para o `audit-service` (§3.1 #10); a trilha em si não mora mais aqui.

#### 3. Billing, Quotas & Usage Metering (`services/billing-service`)
- **Tecnologia**: Python FastAPI / Node.js.
- **Responsabilidades**:
  - Integração com Stripe Billing e Paddle para gestão de assinaturas, faturas automáticas e pagamentos via cartão/invoice corporativo.
  - Telemetria de consumo em tempo real:
    - Segundos de computação de Workers R e Python.
    - Armazenamento de datasets e snapshots no Object Storage (GBs/mês).
    - Execuções de consultas em Data Warehouses externos.
    - Contagem de assentos (*seats*) ativos.
  - Motor de limites de cotas com *soft limits* (notificações por email/webhook aos 80% e 90%) e *hard limits* (bloqueio gracioso de novas análises com upgrade prompt).

#### 4. Data Query & Transformation Engine (`services/data-engine-service`)
- **Tecnologia**: Python com DuckDB, Apache Arrow, Polars e SQLGlot.
- **Responsabilidades**:
  - Gerenciamento de Conexões Externas com pools seguros: PostgreSQL, MySQL, Snowflake, BigQuery, ClickHouse, Redshift, Amazon Athena, MariaDB e S3 Parquet/Delta Lake.
  - Federação de Consultas com DuckDB em memória: execução de queries locais ultrarrápidas sobre arquivos e caches.
  - Data Prep / Recipe Engine:
    - Transformações sem código: filtragem, categorização, criação de colunas calculadas, substituição de nulos, pivot/unpivot, agregação e mescla (*joins*).
    - Validação sintática e AST com SQLGlot para prevenção de SQL Injection e validação de dialetos.
  - Mascaramento e Segurança de Dados:
    - *Row-Level Security* (RLS) dinâmico baseado no perfil do usuário conectado.
    - Mascaramento de colunas sensíveis (PII / LGPD / GDPR) antes da entrega aos estatísticos.

#### 5. Statistical Orchestration Service (`services/stat-orchestrator`)
- **Tecnologia**: Python FastAPI + Celery / RabbitMQ + Redis.
- **Responsabilidades**:
  - Ingestão de pedidos de análise via contratos estritos JSON Schema (especificação unificada de variáveis dependentes, fatores, hipóteses, testes post-hoc, etc.).
  - Cache determinístico distribuído: cálculo do hash do dataset e do payload da análise:
    $$\text{CacheKey} = \text{SHA256}(\text{DatasetFingerprint} \parallel \text{AnalysisSpecJson} \parallel \text{EngineVersion})$$
    Evita reprocessamentos custosos de análises idênticas.
  - Gerenciamento de filas de tarefas com priorização estrita por tier de cliente:
    - Fila `vip-enterprise` (processamento prioritário e workers dedicados).
    - Fila `standard-saas`.
    - Fila `community-batch`.
  - Servidor WebSocket para emissão de progresso passo a passo aos clientes web.

#### 6. Stat Workers Cluster (`engines/r-worker`; Engine B Python embutido no `stat-orchestrator`)
- **Tecnologia**:
  - Worker R: Debian/Ubuntu slim com R 4.3+, `jaspTools`, módulos R oficiais do JASP e `arrow`.
  - Worker Python: Python 3.12 slim com `scipy`, `statsmodels`, `pingouin`, `pymc`, `polars`, `pyarrow`.
- **Mecanismos de Segurança e Escalonamento**:
  - Autoscaling Horizontal via **KEDA** (Kubernetes Event-driven Autoscaling) escalando de 0 a centenas de pods conforme a profundidade da fila RabbitMQ.
  - Sandboxing com limites estritos de `cgroups` (CPU e RAM por container).
  - Execução como usuário sem privilégios (`non-root`).
  - Timeout forçado por análise (ex: 60s standard, 600s enterprise).
  - Sistema de arquivos temporário efêmero em RAM (`tmpfs`), destruído imediatamente após o envio dos resultados para o Object Storage.

#### 7. BI, Reporting & Collaboration Service (`services/bi-report-service`)
- **Tecnologia**: Node.js / TypeScript com NestJS ou Python FastAPI.
- **Responsabilidades**:
  - Gestão de Dashboards com layouts de grid dinâmico (React Grid Layout), cross-filtering interativo e parâmetros globais sincronizados.
  - Editor de Relatórios em blocos:
    - Integração com ProseMirror / TipTap para edição rica.
    - Suporte a blocos dinâmicos de estatística: tabelas em padrão estrito APA 7th, equações LaTeX/KaTeX, gráficos ECharts responsivos e interpretações textuais com IA.
  - Colaboração em Tempo Real utilizando CRDTs com **Yjs** e WebSockets (múltiplos estatísticos e analistas editando o mesmo relatório simultaneamente com presença de cursores).
  - Versionamento de Relatórios: snapshots imutáveis arquivados no S3 com trilha de alterações (revisões históricas restauráveis).

#### 8. Export & Delivery Service (`services/export-service`)
- **Tecnologia**: Node.js com Playwright (Chromium Headless), Python com `python-docx` e LaTeX Compiler.
- **Responsabilidades**:
  - Geração de PDFs de alta fidelidade:
    - Renderização do DOM do relatório em resolução vetorial para impressão.
    - Quebras de página inteligentes (*page-break-inside: avoid* para tabelas APA e gráficos).
    - Numeração dinâmica de páginas, cabeçalhos, rodapés e sumário executivo gerado automaticamente.
  - Exportação nativa de relatórios editáveis para DOCX (Word), PPTX (PowerPoint) e arquivos `.tex` (LaTeX acadêmico).
  - Motor de Agendamento (Cron Scheduler): disparo recorrente de relatórios por e-mail (SendGrid / AWS SES) ou canais corporativos (Slack, Microsoft Teams, Webhooks).

#### 9. Frontend Enterprise (`apps/web`)
- **Tecnologia**: Next.js 15+ (App Router), React 19, TypeScript, Tailwind CSS, shadcn/ui, Apache ECharts, Monaco Editor.
- **Responsabilidades**:
  - Interface do usuário com padrão visual refinado e responsivo.
  - Suporte a temas corporativos (White-labeling com logos, cores da marca e fontes customizadas para planos Enterprise).
  - Pacote `@metastatistic/react-embed`:
    - SDK JavaScript/React para incorporação (*iframe seguro* e *web component*) de dashboards e gráficos estatísticos em sistemas legados dos clientes com autenticação via JWT assinado.

#### 10. Audit Trail (`services/audit-service`)
- **Tecnologia**: Python FastAPI, SQLite próprio (`audit.db`, volume `audit_data`). Alvo: PostgreSQL com tabela *append-only*.
- **Responsabilidades**:
  - Registrar eventos encadeados por hash SHA-256 **por tenant** (`prev_hash` → `record_hash`), para SOC 2 Tipo II e FDA 21 CFR Part 11.
  - `GET /audit/verify`: recalcula as cadeias e aponta o primeiro registro adulterado (com `tenant_id` verifica a cadeia dele; sem, verifica todas separadamente).
  - `GET /audit/export`: eventos em ordem cronológica com atestado de integridade.
  - `POST /audit/events`: ingestão, usada pelo `auth-tenant-service`. Hoje é *best-effort* no chamador (ver §7).
  - `python -m app.import_legacy`: migra eventos da antiga tabela `audit_log` do auth preservando hashes.

---

## 4. Arquitetura de Dados e Persistência

### 4.1 Transição do Armazenamento Monolítico para Nuvem Corporativa

No protótipo inicial, utilizava-se SQLite (`meta.db`) e arquivos CSV locais em disco. Na solução comercial, a arquitetura de persistência é segregada em quatro camadas resilientes:

| Camada | Tecnologia | Propósito | Estratégia de Isolamento Multi-Tenant |
|---|---|---|---|
| **Metadados & Transações** | PostgreSQL 16+ (Amazon RDS / Cloud SQL) | Usuários, organizações, permissões, definições de relatórios, dashboards, queries e conexões | **Pool compartilhado com Row-Level Security (RLS)** nativo para planos Standard; **Schema-per-tenant** ou **Database-per-tenant** para Enterprise VIP |
| **Object Storage** | MinIO / AWS S3 / Cloudflare R2 | Datasets em formato Apache Parquet, snapshots de relatórios, PDFs exportados e artefatos de modelo | Chave de prefixo estruturada: `s3://metastatistic-{region}/{tenant_id}/{workspace_id}/{file_uuid}.parquet` com criptografia SSE-S3 / SSE-KMS |
| **Cache & Sessões** | Redis Cluster 7+ | Cache de queries, sessões de usuário, locks distribuídos e pub/sub para websockets | Keysnamespacing: `tenant:{tenant_id}:cache:{hash}` |
| **Fila de Mensageria** | RabbitMQ / Apache Kafka | Fila de análises estatísticas assíncronas, webhooks e pipelines de exportação | Filas separadas com prioridade por QoS e suporte a Dead-Letter Exchanges (DLX) |

### 4.2 Estratégia de Isolamento Multi-Tenancy no PostgreSQL

```sql
-- Exemplo de isolamento por Row-Level Security (RLS) no PostgreSQL
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON reports
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
```

Para clientes do tier **Enterprise On-Premise**, a persistência é completamente autônoma, operando dentro do cluster Kubernetes da própria empresa, sem nenhuma partilha com outros clientes.

---

## 5. Matriz de Planos Comerciais e Monetização

O modelo de negócio baseia-se em **SaaS B2B baseado em assinatura (com precificação baseada em assentos e valor agregado de computação)**, complementado por licenças corporativas anuais para grandes empresas:

| Recurso / Funcionalidade | Community (Open-Core) | Team (SaaS) | Enterprise SaaS | Enterprise On-Premise / Air-Gapped |
|---|---|---|---|---|
| **Público-Alvo** | Desenvolvedores & Estudantes | Pequenos times e consultorias | Médias e grandes empresas | CROs, Bancos, Defesa e Saúde |
| **Modelo de Cobrança** | Gratuito (Auto-hospedado) | $49/usuário/mês | $149/usuário/mês (mín. 10) | Contrato Anual Customizado |
| **Engine Estatístico** | Engine A (JASP R AGPL) | Engine A (JASP R) | Engine A ou Engine B (Dual) | **Engine B (100% Proprietário)** |
| **Isolamento de Dados** | Local / SQLite | Multi-Tenant (RLS) | Multi-Tenant (Schema Dedicado) | **Single-Tenant Totalmente Privado** |
| **SSO & Governança** | E-mail / Senha simples | E-mail / Google Auth | SAML 2.0, Okta, Azure AD, SCIM | SAML 2.0, SCIM, LDAP Local |
| **Conectores de Banco** | CSV / SQLite / Postgres | Postgres, MySQL, BigQuery | Todos + Snowflake, Athena, Databricks | Conectores customizados e VPC Peering |
| **Capacidade de Computação** | 1 Worker local | Fila compartilhada | **Workers dedicados (KEDA)** | **Cluster local autônomo** |
| **Embeddable Analytics SDK** | ❌ Não disponível | ❌ Não disponível | ✅ Sim (com marca d'água) | ✅ Sim (White-label total) |
| **Suporte & SLAs** | Fórum GitHub | Horário Comercial (e-mail) | 99.9% SLA + Gerente Dedicado | 99.99% SLA + Suporte 24/7/365 |
| **Certificações & Compliance**| Nenhuma | Termos padrão | SOC 2 Tipo II, HIPAA BAA | 21 CFR Part 11, GxP, ISO 27001 |

> **⚠️ Preços divergentes no repositório (decisão pendente).** Existem três tabelas diferentes:
> | Fonte | Team | Enterprise |
> |---|---|---|
> | Esta matriz (§5) | US$ 49 / usuário / mês | US$ 149 / usuário / mês (mín. 10) |
> | `README.md` (plano de negócio, atividade 9) | R$ 249 / mês (R$ 199 no anual) | R$ 1.490 / mês |
> | **Implementado** (`services/billing-service/app/config.py`, `PricingModal.tsx`) | US$ 49 / mês (US$ 490 / ano) | US$ 299 / mês (US$ 2.990 / ano), **por organização**, não por usuário |
>
> Só a última é o que a plataforma realmente cobra hoje. Antes de ir ao ar é preciso escolher o modelo (por assento × por organização) e a moeda, e alinhar as três fontes.

---

## 6. Roteiro Fases de Implementação (Roadmap)

### Fase 1: Preparação do Fork e Desacoplamento de Contratos (Semanas 1–2) — ✅ núcleo concluído (2026-11-06), itens de persistência pendentes
- [x] Inicialização da estrutura Monorepo (pnpm) com:
  - [x] `packages/contracts`: contratos TypeScript para tenancy, análises/APA, queries e storage.
  - [ ] `packages/sdk`: SDK cliente em TypeScript — **não criado** (o consumo é pelo `apps/web/src/api.ts`; `packages/react-embed` cobre o caso de embutir).
  - [ ] `packages/ui`: design system compartilhado — **não criado** (estilos vivem em `apps/web`).
- [ ] Refatoração da persistência:
  - [ ] PostgreSQL com migrações Alembic / Prisma — **pendente**; todos os serviços usam SQLite (ver §7).
  - [ ] `tenant_id` sistemático em todas as entidades — **parcial**: `apps/api` tem tabela `tenants` e o BI/auth isolam por `X-Tenant-ID`; sem auditoria completa do isolamento.
- [x] Abstração de armazenamento de objetos (`StorageProvider`) com backends `local` e `s3` em `apps/api/app/storage/`. (Execução com MinIO local não verificada.)

### Fase 2: Gateway, Auth Multi-Tenant e Billing (Semanas 3–5) — ✅ concluída (2026-11-06; billing na Fase 7)
- [x] Implementação do serviço `auth-tenant-service`:
  - [x] Organizações e Gestão de Convites. [ ] *Workspaces* — **não implementados** (existem só como tipo em `packages/contracts`).
  - [x] RBAC (`owner`, `admin`, `statistician`, `analyst`, `viewer`) com proteção ao owner e cotas por tier.
- [x] API Gateway (`services/gateway`) com roteamento por subdomínio / `X-Tenant-ID` / JWT. [ ] Terminação TLS — **não implementada no gateway** (o Helm chart prevê Ingress TLS).
- [x] Serviço `billing-service`: webhooks do Stripe (criação, atualização, cancelamento) — entregue na Fase 7.
  - [ ] Middleware de **medição de uso** — não implementado; o enforcement de cotas limita membros/datasets/armazenamento por tier no auth.

### Fase 3: Separação do Data Engine e Conectores SQL (Semanas 6–8) ✅ CONCLUÍDA (2026-11-07)
- [x] Extração da lógica de consulta para o microsserviço `data-engine-service`:
  - Conectores externos para SQLite, DuckDB, PostgreSQL e MySQL com verificação de conectividade e latência.
  - Integração do DuckDB em memória com conversão zero-copy para streaming Apache Arrow IPC (`POST /queries/arrow`).
  - Execução de queries em sandbox confinada com validação AST via SQLGlot e bloqueio de DDL/DML.
- [x] Refatoração do Data Prep / Recipe Engine:
  - Execução de etapas de transformação via AST do SQLGlot e DuckDB (`POST /transforms/preview`).
  - Mascaramento dinâmico de PII (email, CPF, telefone, redaction e SHA-256 salgado com isolamento de tenant).
- [x] Integração no API Gateway e Docker Compose:
  - Roteamento de `/api/v1/queries/*`, `/api/v1/transforms/*` e `/api/v1/connections/*` no Gateway.
  - Healthcheck unificado agregando `data-engine-service`.
  - Serviço `data-engine-service` configurado no `docker-compose.yml` (porta 8014:8004).

### Fase 4: Orquestração e Cluster de Workers com Autoscaling (Semanas 9–11) ✅ CONCLUÍDA (2026-11-06)
- [x] Construção do microsserviço `stat-orchestrator`:
  - Fila assíncrona de jobs com suporte a prioridade por tier (VIP Enterprise vs Standard) e controle de concorrência.
  - Implementação do cache LRU determinístico de análises (hash de tenant, dataset, opções e colunas).
  - API com endpoints `/health`, `/analyses/status`, `/jobs/submit`, `/jobs/{job_id}` e `/analyses/run`.
- [x] Construção e empacotamento dos containers de Workers e Orquestração:
  - R Engine Adapter com forward para workers R e healthcheck ativo.
  - Integração no API Gateway e orquestração Docker Compose (`docker-compose.yml`).
- [x] Início e implementação do **Engine B** em Python (`scipy`, `numpy`) para independência total de AGPL:
  - Estatísticas Descritivas (`descriptives`).
  - Teste t Independente (`ttest_independent`) e Teste t de Uma Amostra (`ttest_onesample`).
  - ANOVA One-Way (`anova`).
  - Correlação de Pearson (`correlation`).
  - Formatação rigorosa de tabelas e notas conforme APA 7th.
  - Roteamento Dual-Engine inteligente ('py', 'r', 'auto').

### Fase 5: Microsserviço de Relatórios, BI e Exportação (Semanas 12–14) ✅ CONCLUÍDA (2026-11-07)
- [x] Implementação do serviço `bi-report-service`:
  - CRUD com bloqueio otimista de versão (conflito 409) para relatórios e dashboards.
  - Snapshots imutáveis de versão com restauração instantânea.
  - Dashboards reativos com grade flexível de tiles e suporte a filtros multi-dimensionais.
  - Colaboração em tempo real via WebSockets (`/ws/reports/{report_id}`).
  - Isolamento multi-tenant estrito via `X-Tenant-ID`.
- [x] Desenvolvimento do serviço `export-service`:
  - Exportação HTML editorial e PDF com CSS Paged Media (`@page { size: A4; margin: 2.5cm; }`) e tabelas APA 7th.
  - Gerador de exportação para LaTeX acadêmico com pacotes `booktabs` e `amsmath`.
  - Gerador de exportação para Microsoft Word DOCX via `python-docx` com estilos e tabelas APA.
  - Gerador de exportação para Markdown GFM com blocos matemáticos KaTeX.
  - Roteador polimórfico unificado em `POST /export/generate`.
- [x] Desenvolvimento e publicação do pacote `@metastatistic/react-embed`:
  - Componente React seguro embutível via iframe com sandbox restritivo.
  - Sincronização bidirecional de eventos e comandos via `postMessage`.
  - Redimensionamento automático dinâmico (`autoResize`), suporte a temas (`light`/`dark`) e filtros.
- [x] Atualização do API Gateway e Docker Compose com proxy reverso e healthcheck integrado.

### Fase 6: Prontidão Enterprise, Segurança e Lançamento (Semanas 15–16) ✅ CONCLUÍDA (2026-11-09)
- [x] Implementação de SSO corporativo (SAML 2.0 / Okta / Azure AD / OIDC) com provisionamento Just-In-Time (JIT) em `services/auth-tenant-service/app/sso.py`.
- [x] Implementação de provisionamento de identidades SCIM 2.0 (RFC 7643 e RFC 7644) com suporte a Okta e Azure AD (`/scim/v2/tenants/{tenant_id}/*`).
- [x] Implementação de Trilha de Auditoria imutável (*Audit Logs*) criptograficamente encadeada com SHA-256 (Merkle/blockchain-style) e verificação matemática de adulteração em tempo real para conformidade com SOC 2 Tipo II e FDA 21 CFR Part 11 em `services/auth-tenant-service/app/audit_trail.py` (**movido para `services/audit-service` na Fase 8**).
- [x] Atualização de rotas no API Gateway (`services/gateway/app/proxy.py`) para rotear SSO, SCIM 2.0 e Audit Trail.
- [x] Criação de Helm Charts oficiais Kubernetes Enterprise (`deploy/helm/metastatistic`) com `Chart.yaml`, `values.yaml`, HPA, Ingress TLS, ConfigMap, Secrets e pares Deployment/Service para os 7 microsserviços.
- [x] Testes automatizados completos de SSO, SCIM, Auditoria com teste de adulteração física direta no banco e 100% de aprovação (56 testes backend no monorepo).
- [x] Documentação técnica detalhada em `docs/commercial-phase6-progress.md`.

### Fase 7: Microsserviço de Billing e Monetização Stripe ✅ CONCLUÍDA (2026-11-09)
- [x] Implementação do microsserviço `services/billing-service` (FastAPI, SQLite, Stripe SDK):
  - Catálogo de planos comerciais (Community Free, Team $49/mês, Enterprise $299/mês).
  - Checkout Sessions Stripe (`POST /billing/checkout`) com suporte a modo mock seguro em dev/testes.
  - Customer Portal Stripe (`POST /billing/portal`) para gestão de cartões e faturamento.
  - Histórico financeiro e faturas multi-tenant (`GET /billing/invoices`).
  - Webhooks Stripe (`POST /billing/webhook`) tratando ativação de assinaturas, atualizações, cancelamentos com downgrade e faturas pagas/falhas.
- [x] Atualização de `services/auth-tenant-service`:
  - Endpoint `PATCH /tenants/{tenant_id}/tier` para reajuste dinâmico de cotas e registro de auditoria.
- [x] Atualização do API Gateway (`services/gateway`):
  - Proxy para rotas de billing e monitoramento de saúde integrado.
- [x] Orquestração Docker Compose e Helm Charts:
  - Adicionado `billing-service` (8017:8007), volume `billing_data`, templates de deployment, service e HPA.
- [x] Suite de testes automatizada (67 testes passando 100% no monorepo backend).
- [x] Documentação em `docs/commercial-billing-progress.md`.

### Fase 8: Produto Unificado, Onboarding e Extração da Auditoria ✅ CONCLUÍDA (2026-11-09 → 2026-11-11)
- [x] **Frontend único atrás do gateway** (`docs/commercial-frontend-unification.md`): `/` e assets servidos via `WEB_URL`, normalização de `/api/*` → `/api/v1/*`, modal de planos (`PricingModal`) integrado ao `billing-service`.
- [x] **Onboarding B2B**: autenticação ligada por padrão no compose, cadastro self-service e login/registro fluidos, seletor de workspace (organização) e convite de membros, landing page pública com `AuthGate`. Rotas de sessão do frontend (`/auth/login`, `/auth/me`…) roteadas para a `apps/api`.
- [x] **Plano de negócio** (atividade 9) e mapa de reaproveitamento em `README.md` e `docs/plano-de-negocio.md`.
- [x] **Infra**: stack consolidada em um único `docker-compose.yml`; portas de host parametrizáveis (`GATEWAY_PORT` padrão 8085, `API_PORT` padrão 8020, `R_WORKER_PORT` padrão 8011) para convivência em VPS.
- [x] **Extração do `audit-service`** (2026-11-11):
  - Serviço novo (porta 8008 / exposta 8018) com banco e volume próprios; lógica de hash chain movida sem alteração do `auth-tenant-service`.
  - `auth-tenant-service` passou a enviar eventos por HTTP (`AuditClient`, *best-effort*) e deixou de expor `/audit/*`.
  - Gateway roteia `/audit` e `/api/v1/audit` para o novo serviço e o inclui no `/health` agregado. Compose e Helm (deployment, service, configmap, values, HPA) atualizados.
  - `python -m app.import_legacy` migra eventos antigos preservando hashes (idempotente).
  - **Correção**: `GET /audit/verify` sem `tenant_id` verificava uma cadeia global, mas a gravação encadeia por tenant, gerando falso "Broken hash chain" com 2+ tenants. Agora cada cadeia é verificada separadamente.
  - Verificado: testes unitários (audit 10, auth 17, gateway 12) e ponta a ponta em Docker (eventos via gateway, persistência após restart, detecção de adulteração direta no SQLite, degradação com o audit fora do ar, import legado). Helm **não** foi validado (sem `helm` disponível).

---

## 7. Dívida Técnica e Próximos Passos

Ordenados por risco para um lançamento com clientes regulados.

### Segurança e conformidade
- [ ] **🔴 Isolamento de tenant não é imposto (verificado em 2026-11-11).** O gateway resolve o tenant por `X-Tenant-ID` → subdomínio → claim `tenant_id` de um JWT **cuja assinatura nunca é verificada** (`services/gateway/app/tenant_resolver.py` só decodifica o payload; `jwt_secret_key` do gateway não é usada), e os serviços confiam no header. Testado contra uma stack real: sem nenhuma credencial, apenas com `X-Tenant-ID: <outro tenant>` foi possível ler `/billing/subscription`, `/billing/invoices` e `/audit/events` desse tenant; um JWT com assinatura inválida e `tenant_id` alheio também foi aceito. Correção: o gateway verifica a assinatura (HS256 com `JWT_SECRET_KEY`), **descarta** `X-Tenant-ID`/`X-Tenant-Slug` vindos do cliente e injeta o tenant do token; serviços internos só aceitam o header vindo do gateway (rede interna / segredo de serviço).
- [ ] **`audit-service` sem autenticação/autorização.** Qualquer chamador que alcance o serviço pode `POST /audit/events` (forjar eventos) e ler eventos de qualquer tenant via `?tenant_id=`. Exigir JWT/serviço-a-serviço, restringir o `POST` à rede interna (não rotear pelo gateway) e limitar leitura ao tenant do token.
- [ ] **Entrega de eventos de auditoria é *best-effort*.** Se o `audit-service` estiver fora do ar, o evento é perdido (só há log de erro). Para 21 CFR Part 11: *outbox* + retry no `auth-tenant-service`, ou falhar fechado nas operações críticas.
- [ ] **Imutabilidade só criptográfica.** A cadeia *detecta* adulteração, mas o SQLite permite `UPDATE`/`DELETE`. Alvo: tabela *append-only* (PostgreSQL com permissões restritas / triggers) e âncora periódica do último hash fora do banco.
- [x] **Segredos padrão no código** — tratado em 2026-11-11: `.env.example` + variáveis no compose e no Helm; com `ENVIRONMENT=production`, `auth-tenant-service`, `gateway` e `billing-service` recusam iniciar com `JWT_SECRET_KEY` padrão/curta, `STRIPE_MOCK_MODE=true` ou credenciais Stripe de dev (erros não imprimem os valores). Ficam fora: `apps/api` (sem segredo próprio hardcoded) e a aplicação efetiva do JWT pelo gateway (item acima).

### Consistência do produto
- [ ] **Dois logs de auditoria coexistem.** `apps/api/app/audit.py` (SQLite simples, sem hash, lido por `apps/web/src/components/AuditLog.tsx` em `GET /audit?before_id=&action=`) e o `audit-service` (cadeia SHA-256, `/audit/events`). Pelo gateway, `/audit` agora cai no segundo, com outro formato; a tela de auditoria do frontend provavelmente não funciona via gateway. Decidir: o `apps/api` passa a emitir eventos ao `audit-service` e o front lê dele.
- [ ] **Preços divergentes** entre README, PLAN §5 e `billing-service` (ver nota na §5).

### Infraestrutura e dados
- [ ] **PostgreSQL** (multi-tenant com RLS) no lugar de SQLite por serviço; Alembic para migrações.
- [ ] **Fila/cache distribuídos** (Redis, RabbitMQ/Kafka) no `stat-orchestrator`; hoje fila e cache LRU são em memória por processo.
- [ ] **Object storage** (MinIO/S3) em uso real nos serviços; hoje só a abstração `StorageProvider` existe no `apps/api`.
- [ ] **Helm**: validar com `helm lint`/`helm template` e testar num cluster; definir volumes persistentes para os serviços com SQLite.
- [ ] **TLS** no ponto de entrada (Ingress) e observabilidade (OpenTelemetry, `X-Correlation-ID`) previstas na §3.1 mas não implementadas.

### Funcionalidades do plano ainda não feitas
- [ ] *Workspaces* e hierarquia de papéis ampliada (`Org Admin`, `Workspace Admin`, `Data Engineer`, `Senior Statistician`).
- [ ] Medição de uso (segundos de worker, GB, consultas) e *soft/hard limits* com notificação (§3.1 #3).
- [ ] `packages/sdk` e `packages/ui`.
- [ ] Opção Enterprise On-Premise / *air-gapped* da §5.
