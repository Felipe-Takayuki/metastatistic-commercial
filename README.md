# Metastatistic Commercial — Plano de Negócio & Arquitetura SaaS

> **ISW055 · Atividade 9 — Fork e Plano de Negócio**  
> **Professor**: Allan Siriani ([github.com/siriani](https://github.com/siriani))  
> **Projeto**: Metastatistic Commercial (B2B SaaS de Business Intelligence & Rigor Estatístico)  
> **Repositório**: [metastatistic-commercial](https://github.com/Felipe-Takayuki/metastatistic-commercial)
>
> **Entregas**: [Atividade 9 — plano de negócio](docs/plano-de-negocio.md) · [Atividade 10 — negócio no ar](docs/atividade-10-negocio-no-ar.md) · [Atividade 11 — SaaS com Stripe](docs/atividade-11-saas-stripe.md) · [P2 — relatório consolidado (PDF)](docs/P2_ISW055_Felipe_Takayuki_Tanaka_Takahashi.pdf) · [Evidências (prints com data e hora)](docs/evidencias/)

---

## 📋 Sumário Executivo do Plano de Negócio

### 1. Nome e Frase
* **Nome do Produto**: **Metastatistic** (*Metastatistic Commercial*)
* **Frase-resumo**: *A plataforma SaaS que une a agilidade visual e preparação de dados sem código do Business Intelligence ao rigor estatístico inferencial e relatórios automatizados no padrão APA 7th para pesquisadores, bioestatísticos e equipes de P&D clínico.*

---

### 2. A Dor
* **Quem sofre**: Bioestatísticos, pesquisadores de ensaios clínicos, epidemiologistas, cientistas de dados translacionais e analistas de P&D de hospitais, laboratórios farmacêuticos e instituições de pesquisa científica.
* **Quando ocorre**: Sempre que precisam transformar dados brutos (de prontuários, ensaios laboratoriais, CSVs ou bancos SQL) em relatórios regulatórios, evidências de ensaios ou publicações para periódicos científicos indexados com revisão por pares.
* **Quanto custa hoje**:
  * **Dinheiro**: Licenças astronômicas de pacotes legados fechados (ex.: IBM SPSS a partir de R$ 15.000/ano por estação de trabalho; SAS com contratos anuais de dezenas de milhares de dólares), além de consultorias bioestatísticas externas cobrando entre R$ 200 e R$ 500 por hora.
  * **Tempo**: Entre 15 a 40 horas semanais por pesquisador gastas em retrabalho manual exaustivo: limpeza de planilhas no Excel, colagem de dados no SPSS/JASP, recalibração de modelos em scripts locais de R/Python e digitação manual linha por linha de tabelas no Microsoft Word para se adequar às exigências formais da APA (American Psychological Association) 7ª Edição.
  * **Risco**: Risco crítico de erro humano de transcrição (copy-paste), ausência de trilha de auditoria (audit trail) exigida por órgãos regulatórios (FDA 21 CFR Part 11, ANVISA, SOC 2 Type II) e risco de retratação ou rejeição de artigos científicos por falhas de reprodutibilidade metodológica.
* **Como essa pessoa resolve hoje**:
  * Exporta arquivos CSV desestruturados e sem higienização;
  * Manipula colunas em planilhas Excel suscetíveis a corrupção silenciosa de dados e erros de formatação;
  * Executa análises em softwares desktop locais mono-usuário (SPSS ou JASP local), sem suporte a trabalho colaborativo em nuvem;
  * Redesenha manualmente tabelas no Word/Docs, ajustando itálicos de estatísticas ($t$, $F$, $p$, $d$, $\text{BF}_{10}$) e notas de rodapé;
  * Não possui controle de versão, governança de inquilinos ou mascaramento de dados sensíveis de pacientes (violando LGPD e HIPAA).

---

### 3. Persona
* **Nome fictício**: Dra. Camila Valente
* **Idade**: 36 anos
* **Cargo**: Coordenadora de Pesquisa Clínica e Bioestatística em um Centro Oncológico e Professora Adjunta de Pós-Graduação.
* **Rotina**:
  * Supervisiona simultaneamente 4 ensaios clínicos multicêntricos com novas drogas imunoterápicas, lidando com milhares de pacientes e dezenas de biomarcadores.
  * Divide sua semana entre validações de protocolos médicos, conferência de prontuários eletrônicos coletados e redação de manuscritos para periódicos de alto fator de impacto (*The Lancet Oncology*, *NEJM*).
* **O que tenta fazer**:
  * Importar grandes volumes de dados clínicos, testar hipóteses (testes t de Welch, ANOVA com post-hoc de Tukey/Bonferroni, regressões logísticas e testes Bayesianos com Fatores de Bayes) e produzir gráficos e tabelas editoriais prontas para publicação e auditorias regulatórias.
* **O que a atrapalha**:
  * As ferramentas corporativas de BI (Power BI, Metabase, Tableau) geram gráficos atraentes de contagem e média, mas **não fazem inferência estatística** (não calculam p-valores corrigidos, intervalos de confiança de 95%, tamanhos de efeito ou premissas de normalidade/homocedasticidade), nem conhecem o padrão editorial APA 7th.
  * O SPSS instalado na máquina do hospital é arcaico, mono-usuário e não roda em nuvem. Seus orientandos e colegas de equipe não têm acesso às mesmas licenças.
  * Camila perde finais de semana formatando tabelas no Word e conferindo se alguém não alterou uma célula de dados por engano, sem conseguir comprovar a cadeia de custódia matemática exigida pela comissão de ética e auditorias da GCP/FDA.

---

### 4. Concorrentes e Alternativas

| Concorrente / Alternativa | O que é | O que faz mal (Gargalos) |
| :--- | :--- | :--- |
| **IBM SPSS Statistics / SAS** | Softwares proprietários legados de análise estatística desktop. | Custo de licença proibitivo (milhares de reais por assento), interface obsoleta, instalador local mono-usuário sem nuvem colaborativa nativa, sem dashboards interativos e sem APIs modernas. |
| **Power BI / Tableau / Metabase** | Plataformas tradicionais de Business Intelligence corporativo. | Focadas apenas em agregações simples (soma, contagem, média). **Zero capacidade estatística inferencial**: não calculam testes de hipóteses, $p$-valores, testes bayesianos ou premissas, e não geram relatórios acadêmicos/regulatórios. |
| **Planilhas (Excel / Google Sheets) + "Jeito de Sempre"** | Manipulação e cálculo manual em planilhas com tabelas no Word. | Não possuem governança nem trilha de auditoria; quebram com grandes datasets; taxas elevadas de erro humano em fórmulas; formatação manual lenta; não atendem LGPD/HIPAA ou FDA 21 CFR Part 11. |
| **JASP Desktop / RStudio** | Ferramentas estatísticas de código aberto excelentes em rigor científico. | São aplicações desktop locais. Não possuem arquitetura SaaS em nuvem, gestão multi-tenant de times e organizações, controle de cotas corporativas, publicação de dashboards interativos web nem integração direta com gateway de pagamentos. |

---

### 5. Proposta de Valor
> *"Transforme dados brutos em relatórios estatísticos e publicações científicas no padrão estrito APA 7th em minutos — combinando a facilidade visual e data prep do Metabase ao rigor inferencial do JASP, diretamente na nuvem e com conformidade regulatória para equipes."*

---

### 6. Modelo de Receita com Stripe

O modelo de monetização é um SaaS B2B **Freemium** com assinatura recorrente **mensal em R$** via **Stripe Checkout & Customer Portal**. Dois planos são vendidos pelo próprio produto; o Enterprise é contrato sob medida (fora do Stripe):

```
              ┌──────────────────────────────┐         ┌──────────────────────────────────┐
              │            FREE              │         │               PRO                │
              │          R$ 0 / mês          │  ─────▶ │        R$ 249,00 / mês           │
              │  • até 3 usuários            │ Stripe  │  • até 15 usuários               │
              │  • até 5 datasets (10 MB)    │ Checkout│  • até 100 datasets (200 MB)     │
              │  • análises essenciais       │         │  • catálogo completo (ANOVA,     │
              │  • relatórios c/ marca d'água│         │    ANCOVA, não paramétricos, BF) │
              └──────────────────────────────┘         │  • conectores SQL, exportação    │
                                                       └──────────────────────────────────┘
```

| | **Free** | **Pro** |
| :--- | :--- | :--- |
| Preço | R$ 0 | **R$ 249,00 / mês** (assinatura recorrente, cancelável no portal) |
| Usuários por organização | 3 | 15 |
| Datasets | 5, de até 10 MB cada | 100, de até 200 MB cada |
| Análises | essenciais | catálogo completo |
| Quem usa | estudantes, pesquisadores individuais | laboratórios, clínicas, consultorias estatísticas |

**Os limites valem na API**, não só na tela: passar do limite de datasets, do tamanho do arquivo ou de usuários responde com uma mensagem que diz o limite do plano e como liberar mais (ex.: *"Limite do plano Free: até 5 datasets por organização (você já tem 5). Faça upgrade para o plano Pro (menu Planos > Assinar o Pro) para liberar até 100 datasets e arquivos maiores."*). Detalhes e prints em [`docs/atividade-11-saas-stripe.md`](docs/atividade-11-saas-stripe.md).

Nomes internos: `free` = tier `community`, `pro` = tier `team` (o `auth-tenant-service` e o gateway já usavam esses nomes). O tier `enterprise` continua existindo para contratos (SSO SAML/OIDC, SCIM 2.0, trilha de auditoria imutável), sem preço no Stripe.

---

### 7. Métricas de Sucesso

| Métrica | Definição | Meta Inicial (6 meses) | Meta de Escala (12 meses) |
| :--- | :--- | :--- | :--- |
| **Cadastros Ativos** | Novos usuários registrados na plataforma. | 1.000 usuários cadastrados | 5.000 usuários |
| **Taxa de Ativação** | Usuários que sobem um dataset e geram a 1ª análise estatística nos primeiros 10 min. | $\ge 60\%$ de ativação | $\ge 75\%$ de ativação |
| **Assinantes Pagantes** | Organizações com assinatura Pro ativa. | 35 equipes pagantes | 150 equipes pagantes |
| **MRR (Receita Recorrente)** | Receita mensal recorrente gerada via Stripe Subscriptions. | R$ 15.000,00 / mês | R$ 65.000,00 / mês |
| **Churn Rate Mensal** | Percentual de cancelamento de planos pagos por mês. | $< 3\%$ ao mês | $< 1.5\%$ ao mês |
| **LTV / CAC** | Razão entre valor de tempo de vida do cliente e custo de aquisição. | $\ge 3:1$ | $\ge 5:1$ (viralidade acadêmica) |

---

### 8. Lean Canvas (Os 9 Blocos)

| Bloco | Conteúdo Estratégico do Metastatistic |
| :--- | :--- |
| **1. Problema** | 1. Pacotes estatísticos tradicionais (SPSS/SAS) são excessivamente caros, locais e difíceis de usar em equipe.<br>2. Ferramentas de BI corporativo (Power BI/Metabase) não fazem inferência científica nem formatam em APA 7th.<br>3. Pesquisadores perdem dezenas de horas semanais limpando dados no Excel e formatando tabelas no Word, correndo risco de erros manuais graves e reprovação regulatória (FDA/SOC 2). |
| **2. Segmentos de Clientes** | • **Early Adopters**: Pesquisadores acadêmicos, bioestatísticos, pós-graduandos e médicos residentes que publicam frequentemente.<br>• **Mercado Corporativo**: Hospitais universitários, laboratórios farmacêuticos, CROs (Organizações de Pesquisa Clínica) e consultorias analíticas. |
| **3. Proposta Única de Valor** | *A agilidade visual do BI corporativo aliada ao rigor estatístico e relatórios automatizados no padrão editorial APA 7th em nuvem multi-tenant.* |
| **4. Solução** | 1. **Data Prep Visual & SQL** acelerado por DuckDB e Apache Arrow IPC (zero cópia de memória).<br>2. **Catálogo Inferencial Completo**: Testes paramétricos, não-paramétricos e estatística Bayesiana ($\text{BF}_{10}$) automatizados.<br>3. **Exportador APA 7th**: Geração nativa com 1 clique de relatórios em PDF Paged Media, DOCX e LaTeX prontos para submissão. |
| **5. Canais** | • Citações em artigos acadêmicos (*Powered by Metastatistic* no rodapé de tabelas geradas no plano gratuito).<br>• Apresentações e workshops em congressos científicos, simpósios de bioestatística e saúde pública.<br>• Parcerias com programas de pós-graduação e ligas de pesquisa universitária.<br>• Marketing de conteúdo técnico (tutoriais de estatística prática, guias de APA 7th e comparação de modelos). |
| **6. Fontes de Receita** | • Assinatura mensal via Stripe: plano Pro a R$ 249/mês (o Free é a porta de entrada).<br>• Contratos Enterprise sob medida para redes hospitalares, CROs e biobancos (SSO, SCIM, auditoria regulatória). |
| **7. Estrutura de Custos** | • Infraestrutura de nuvem (instâncias de computação para microsserviços, DuckDB e workers R/Python).<br>• Armazenamento de objetos (MinIO / AWS S3 para datasets e snapshots Parquet).<br>• Taxas de processamento de pagamentos do Stripe (gateway de faturamento).<br>• Custos de manutenção de domínio, certificados TLS e ferramentas de CI/CD. |
| **8. Métricas-Chave** | • Taxa de ativação de novos cadastros (1ª análise estatística em < 10 min).<br>• Número de relatórios e tabelas APA 7th exportadas por semana.<br>• MRR (Receita Recorrente Mensal) e Net Revenue Retention (NRR).<br>• Taxa de conversão de organizações Free para Pro. |
| **9. Vantagem Injusta** | • **Motor Dual-Engine híbrido**: Combina a robustez e validação do ecossistema R com a velocidade em memória do DuckDB e a portabilidade do SciPy puro, sem infringir licenças restritivas de código aberto.<br>• **Mecanismo de exportação com tipografia editorial estrita** que replica com precisão cirúrgica as normas do manual APA 7th, eliminando a concorrência de ferramentas genéricas de BI. |

---

### 9. Mapa de Reaproveitamento da Arquitetura

Conforme os requisitos da disciplina, absolutamente nada da arquitetura original construída ao longo do curso é descartado. Cada componente de software, banco de dados e microsserviço ganha uma atribuição direta no novo negócio:

| Peça do Projeto Atual | O que vira no SaaS (Metastatistic) | Exemplo Prático de Negócio |
| :--- | :--- | :--- |
| **Catálogo de Filmes (TMDB)** | **Catálogo de Datasets e Análises Estatísticas** | Tabela de dados clínicos (ex.: ensaio de glicemia), esquema de colunas, níveis de medida (nominal, ordinal, contínuo) e biblioteca de testes estatísticos. |
| **Microsserviço de Login + RBAC** | **Gestão de Inquilinos (Multi-Tenancy), SSO e Permissões** | Papéis corporativos de negócio: `admin` (gestor do laboratório), `editor` (pesquisador/analista) e `viewer` (auditor/leitor), com autenticação SSO SAML/OIDC e SCIM 2.0. |
| **Logs e Auditoria (Redis)** | **Trilha de Auditoria Criptográfica Imutável (Audit Trail)** | Registros em cadeia de hash SHA-256 com verificação de integridade matemática: `"dataset_uploaded"`, `"analysis_executed"`, `"report_exported"`, em conformidade com **FDA 21 CFR Part 11**. Implementado em `services/audit-service` (SQLite próprio; sem Redis). |
| **Upload e Perfil (MinIO / S3)** | **Armazenamento Seguro de Datasets e Snapshots** | Upload de grandes arquivos CSV/Parquet de dados de pacientes, fotos/avatares de perfil dos cientistas e snapshots versionados de relatórios. |
| **Plano Premium (Stripe)** | **Microsserviço de Billing & Assinaturas Recorrentes** | Gestão automatizada dos planos Free e Pro com Stripe Checkout, Customer Portal, webhooks idempotentes e sincronização de cotas. |
| **Swagger, CI/CD e Observabilidade** | **Documentação OpenAPI, Helm Charts Kubernetes & Testes** | Contratos canônicos OpenAPI (`@metastatistic/contracts`), esteira de testes automatizados (Vitest/Pytest), healthcheck centralizado no Gateway e deploy em containers. |

---

### 10. Backlog no GitHub

O backlog vive nas *issues* do repositório (rótulo `enhancement`). A entrega de cada atividade é uma issue própria; as demais são o que ainda falta, em ordem de risco:

| Issue | Tipo | Assunto |
| :--- | :--- | :--- |
| [#1](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/1) | Entrega | Atividade 9 — Fork e Plano de Negócio |
| [#9](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/9) | Entrega | Atividade 10 — Seu negócio no ar |
| [#10](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/10) | Entrega | Atividade 11 — SaaS completo com Stripe |
| [#11](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/11) | Entrega | P2 — Relatório consolidado |
| [#2](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/2) | Backlog | Isolar os dados do `apps/api` por organização (tenant) |
| [#3](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/3) | Backlog | Stripe real em modo de teste (produto Pro, preço, webhook e prints) |
| [#4](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/4) | Backlog | Cota de armazenamento e medição de uso por plano |
| [#5](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/5) | Backlog | Unificar identidade (usuários do `apps/api` × `auth-tenant-service`) |
| [#6](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/6) | Backlog | PostgreSQL com migrações no lugar dos SQLite por serviço |
| [#7](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/7) | Backlog | Observabilidade (logs estruturados, correlation id e métricas) |
| [#8](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/8) | Backlog | Reconciliação dos webhooks do Stripe (eventos fora de ordem e falhas) |

Já entregues e que aparecem nas fichas das atividades: modelagem e ingestão com DuckDB, RBAC e isolamento por usuário, landing page pública, billing com Stripe, motor dual-engine e trilha de auditoria (`services/audit-service`, cadeia SHA-256 com `GET /audit/verify`).

---

## 📍 Estado do Projeto

Roadmap completo e dívida técnica em [`PLAN.md`](PLAN.md); relatórios por fase em [`docs/`](docs/).

| Fase | Entrega | Status |
|---|---|---|
| 1–2 | Monorepo, contratos, `auth-tenant-service`, gateway | ✅ (sem `packages/sdk`/`ui`, sem *Workspaces*, ainda em SQLite) |
| 3 | `data-engine-service` (DuckDB, Arrow, PII, conectores) | ✅ |
| 4 | `stat-orchestrator` + Engine B (Python) + Engine A (R/JASP) | ✅ |
| 5 | `bi-report-service`, `export-service`, `@metastatistic/react-embed` | ✅ |
| 6 | SSO SAML/OIDC, SCIM 2.0, trilha de auditoria, Helm | ✅ (Helm não validado em cluster) |
| 7 | `billing-service` com Stripe | ✅ (modo mock por padrão em dev) |
| 8 | Frontend único, onboarding B2B, landing, **`audit-service` extraído** | ✅ |
| — | PostgreSQL, Redis/fila, object storage, medição de uso, TLS | ⬜ pendente |

**Principais pontos em aberto:** o gateway e os serviços confiam no header `X-Tenant-ID` e no `tenant_id` de um JWT cuja assinatura não é verificada — **qualquer cliente consegue ler dados de outro tenant** (verificado em teste, ver `PLAN.md` §7); autenticação no `audit-service`; entrega *best-effort* dos eventos de auditoria; dois logs de auditoria coexistindo (`apps/api` e `audit-service`).

---

## 🏛️ Topologia e Estrutura Técnica do Monorepo

O repositório está organizado como um monorepo moderno gerenciado via `pnpm-workspace.yaml`:

### Microsserviços e Backend
> **Processo `platform`:** no `docker-compose.yml`, `auth-tenant`, `billing`, `bi-report`, `export` e `audit` rodam **no mesmo processo** (`services/platform-service`, sob os prefixos `/_auth`, `/_billing`, `/_bi`, `/_export`, `/_audit`). Cada um continua sendo um app FastAPI independente (com Dockerfile e banco próprios; o Helm segue implantando um a um); juntos economizam ~230 MB de RAM. As portas citadas abaixo valem para a execução individual. No modo `platform` os bancos são `AUTH_`/`AUDIT_`/`BILLING_`/`BI_DATABASE_URL`.

* **`services/gateway`** (porta interna `8080`, exposta em `${GATEWAY_PORT:-8085}`): API Gateway e Edge Router assíncrono com resolução de inquilinos em cascata (subdomínio, cabeçalho `X-Tenant-ID`, JWT Bearer), proxy streaming via `httpx` e healthcheck agregador.
* **`services/auth-tenant-service`** (porta `8002`): IAM, governança de inquilinos (*tenants*), cotas estritas por plano (`community` = Free, `team` = Pro, `enterprise` = contrato), RBAC com proteção ao *owner*, convites criptografados, SSO SAML 2.0 / OIDC e SCIM 2.0 (os eventos de auditoria são enviados ao `audit-service`).
* **`services/stat-orchestrator`** (porta `8003`): Orquestrador de computação analítica com fila assíncrona priorizada por QoS (clientes VIP furam fila), cache determinístico LRU por hash SHA-256 e roteador inteligente Dual-Engine.
* **`services/data-engine-service`** (porta `8004` / exposta `8014`): Motor de consulta analítica em DuckDB Sandbox confinada, streaming binário Apache Arrow IPC (`application/vnd.apache.arrow.stream`), anonimização e mascaramento de PII (LGPD/GDPR), conectores externos (SQLite, DuckDB, PostgreSQL, MySQL) e Data Prep.
* **`services/bi-report-service`** (porta `8005` / exposta `8015`): Microsserviço de relatórios colaborativos e dashboards em tempo real com WebSockets, versionamento e snapshots.
* **`services/export-service`** (porta `8006` / exposta `8016`): Gerador de relatórios multi-formato (HTML/PDF Paged Media APA 7th, LaTeX com booktabs, DOCX com estilos acadêmicos e Markdown GFM).
* **`services/billing-service`** (porta `8007` / exposta `8017`): Microsserviço de monetização e pagamentos Stripe: planos Free e Pro (R$ 249/mês), Checkout Sessions, Customer Portal, faturamento multi-tenant, webhooks idempotentes (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`) com atualização automática do plano e resumo para o painel admin (`GET /billing/admin/summary`).
* **`services/audit-service`** (porta `8008` / exposta `8018`): Trilha de Auditoria Imutável com encadeamento de hash SHA-256 por tenant, verificação de integridade (`/audit/verify`) e exportação com atestado de conformidade (SOC 2 / FDA 21 CFR Part 11). Banco e volume próprios.
* **`apps/api`** (porta interna `8000`, exposta em `${API_PORT:-8020}`): Camada de dados, ingestão de CSV/Parquet via DuckDB, catálogo de datasets, relatórios, dashboards e abstração de storage (`StorageProvider` Local/S3).
* **`engines/r-worker`**: **Engine A (Open Engine)** — Worker R isolado em container com supervisor leve e runtime JASP (tempo limite, recuperação automática, AGPL-compliant).

### Pacotes Compartilhados e Frontend
* **`packages/contracts`**: Contratos canônicos e interfaces TypeScript para entidades multi-tenant, tabelas APA 7th, especificações analíticas e metadados de armazenamento.
* **`packages/react-embed`**: Componente React seguro (`@metastatistic/react-embed`) para incorporação de relatórios, dashboards, gráficos e tabelas APA em aplicações externas via iframe com sandbox e comunicação bidirecional via `postMessage`.
* **`apps/web`**: Aplicação frontend (Vite + React 19 + TypeScript + ECharts) com suporte a análise estatística, construtor de dashboards interativos, editor de relatórios em blocos e visualizações com tema escuro/claro.

---

## 🛠️ Como Executar o Ecossistema

### Execução Completa via Docker Compose
Para subir todo o ecossistema distribuído de microsserviços:
```bash
docker compose up -d --build
```

Serviços acessíveis (a porta do gateway é parametrizável; padrão `8085`):
* **Aplicação Web & API Gateway Único**: `http://localhost:8085`
* **Healthcheck Agregador**: `http://localhost:8085/health` — lista `auth_tenant_service`, `stat_orchestrator`, `data_engine`, `bi_report_service`, `export_service`, `data_api`, `billing_service` e `audit_service`
* **Painel de Pagamentos Stripe (Mock/Live)**: Integrado diretamente no botão "Planos" da interface e no fluxo de upgrade.

### Servidor pequeno (≈1 GB de RAM)
Medido com carga leve, fora Docker/SO: `platform` ~78 MB, `stat-orchestrator` ~170 MB, `data-engine-service` ~110 MB, `api` ~140 MB (+28 MB do boto3), `gateway` ~66 MB, nginx ~7 MB. O que pesa é o **worker R** (limite de 1,5 GB), então a recomendação é rodá-lo em **outra máquina**:
```bash
# máquina do worker R (R_WORKER_TOKEN no .env; + --profile tls para HTTPS com Caddy)
docker compose -f docker-compose.r-worker.yml up -d --build
# servidor principal (R_WORKER_URLS e o mesmo R_WORKER_TOKEN no .env)
docker compose -f docker-compose.yml -f docker-compose.remote-r.yml up -d --build
```
O worker remoto não enxerga o volume de datasets, então a `api` e o `stat-orchestrator` enviam o Parquet ao **edge** (`engines/r-worker-edge`: token Bearer, `PUT /datasets/{id}`, proxy de `/run`) antes da análise; o código R não muda. Sem worker remoto, limite o R com `R_WORKER_MEM_LIMIT` (ex.: `512m`).

**Portainer / servidor único:** `docker-compose.portainer.yml` é um stack autocontido (sem worker R local, sem montar arquivos do host, DuckDB e containers com teto de memória, só o gateway publica porta). Crie um stack do tipo *Repository* apontando para ele e defina `R_WORKER_URLS`, `R_WORKER_TOKEN` e `JWT_SECRET_KEY` (ver o cabeçalho do arquivo).

### Configuração (`.env`)
O compose lê um `.env` na raiz. Há um modelo versionado:
```bash
cp .env.example .env     # o .env não é versionado (.gitignore)
```
Em desenvolvimento tudo é opcional: o que ficar vazio usa valores de desenvolvimento (e os serviços avisam no log). Variáveis:

| Variável | Padrão | Uso |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` ativa a validação de segredos (abaixo) |
| `GATEWAY_PORT` / `API_PORT` / `R_WORKER_PORT` | `8085` / `8020` / `8011` | portas expostas no host |
| `GATEWAY_BIND` / `API_BIND` | `0.0.0.0` | endereço em que `GATEWAY_PORT`/`API_PORT` escutam no host (ex.: `127.0.0.1` atrás de túnel) |
| `AUTH_ENABLED` / `COOKIE_SECURE` | `true` / `false` | sessão do app (`COOKIE_SECURE=true` atrás de HTTPS) |
| `JWT_SECRET_KEY` | chave de dev | assinatura dos JWT (`openssl rand -hex 32`) |
| `STRIPE_MOCK_MODE` | `true` | simula checkout e webhooks |
| `STRIPE_PRICE_ID` / `STRIPE_PRICE_PRO_MONTHLY` | exemplo (só no mock) | ID do preço mensal (R$ 249,00) do plano Pro, criado no Stripe em modo de teste |
| `DATASETS_PRIVATE_BY_DEFAULT` | `true` no compose | dataset novo só é lido pelo dono (e administradores) até ele compartilhar |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | credenciais de dev | Stripe real |

**Produção.** Com `ENVIRONMENT=production`, `auth-tenant-service`, `gateway` e `billing-service` **recusam iniciar** (o container entra em restart com a causa no log) se: `JWT_SECRET_KEY` estiver ausente, for um valor padrão do repositório ou tiver menos de 32 caracteres; `STRIPE_MOCK_MODE=true` (no modo mock o webhook aceita qualquer `Stripe-Signature`, o que permitiria promover um tenant sem pagar); ou as credenciais do Stripe forem as de desenvolvimento. No Helm, defina `secrets.jwtSecretKey`, `secrets.stripeSecretKey` e `secrets.stripeWebhookSecret` (o `values.yaml` vem com placeholders de propósito).

### Testes
Cada serviço Python tem seu ambiente `uv`:
```bash
cd services/<serviço> && uv run pytest        # ex.: audit-service, auth-tenant-service, gateway
cd apps/api && uv run pytest
pnpm test                                      # pacotes e frontend (workspace)
```

### Migrando a auditoria do `auth-tenant-service` (instalações anteriores à Fase 8)
Eventos antigos ficam na tabela `audit_log` do banco do auth. Para trazê-los ao `audit-service` **antes de ele receber tráfego**:
```bash
docker volume ls --format '{{.Name}}' | grep auth_data      # nome real: <projeto>_auth_data
docker compose run --rm -v <projeto>_auth_data:/legacy:ro audit-service \
  python -m app.import_legacy /legacy/auth_tenant.db
```
É idempotente, preserva os hashes e não altera o banco de origem (detalhes em `services/audit-service/README.md`).

---

