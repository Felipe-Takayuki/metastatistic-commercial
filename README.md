# Metastatistic Commercial — Plano de Negócio & Arquitetura SaaS

> **ISW055 · Atividade 9 — Fork e Plano de Negócio**  
> **Professor**: Allan Siriani ([github.com/siriani](https://github.com/siriani))  
> **Projeto**: Metastatistic Commercial (B2B SaaS de Business Intelligence & Rigor Estatístico)  
> **Repositório**: [metastatistic-commercial](https://github.com/Felipe-Takayuki/metastatistic-commercial)

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

O modelo de monetização é um SaaS B2B Freemium com cobrança recorrente via **Stripe Checkout & Customer Portal** (em R$ mensais ou anuais com desconto):

```
                        ┌────────────────────────────────────────────────────────┐
                        │              METRICAS DE PRECIFICAÇÃO SAAS             │
                        └────────────────────────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
  [ Community ]                   [ Team ]                 [ Enterprise ]
     R$ 0/mês                    R$ 249/mês                 R$ 1.490/mês
  • 1 usuário individual      • Até 10 membros           • Usuários ilimitados
  • 5 datasets (50 MB máx)    • Datasets até 2 GB        • Datasets ilimitados
  • Testes frequentistas      • Frequen. + Bayesiano     • Motor Dual-Engine VIP
  • Relatórios c/ marca d'água• PDF/DOCX/LaTeX sem marca • SSO SAML/OIDC + SCIM 2.0
  • Fila compartilhada        • Fila prioritária         • Audit Trail Hash Chain SHA-256
```

> **Nota — preços ainda não unificados.** Os valores em R$ abaixo são os do plano de negócio (atividade 9). A plataforma, porém, hoje cobra em **US$ por organização**: Team US$ 49/mês (US$ 490/ano) e Enterprise US$ 299/mês (US$ 2.990/ano), conforme `services/billing-service/app/config.py` e o modal de planos. O `PLAN.md` (§5) traz ainda uma terceira versão, por usuário. A escolha do modelo e da moeda está pendente — ver `PLAN.md` §5 e §7.

1. **Plano Community (Free — R$ 0 / mês)**:
   * **Público**: Estudantes de graduação, pesquisadores autônomos e experimentadores.
   * **Limites**: 1 usuário individual, até 5 datasets carregados (máx. 50 MB por arquivo), análises estatísticas básicas (Descritivas, Teste t, Pearson), 1 dashboard ativo, relatórios com marca d'água discreta e processamento em fila assíncrona pública.
   * **Objetivo**: Aquisição de base (*bottom-up adoption*), testes de usabilidade e viralidade acadêmica.

2. **Plano Team (Pro — R$ 249 / mês ou R$ 199 / mês no plano anual)**:
   * **Público**: Laboratórios de pesquisa universitária, grupos de pesquisa clínica, clínicas médicas e consultorias estatísticas.
   * **Recursos**: Até 10 membros com controle de acesso baseado em papéis (Admin, Editor, Viewer), datasets ilimitados de até 2 GB por arquivo com aceleração DuckDB/Parquet, catálogo estatístico completo (ANOVA, ANCOVA, testes não-paramétricos e inferência Bayesiana com Fator de Bayes $\text{BF}_{10}$), dashboards ilimitados colaborativos via WebSockets, exportação de relatórios sem marca d'água em múltiplos formatos (PDF Paged Media APA 7th, DOCX e LaTeX com *booktabs*), e fila com prioridade de processamento analítico.
   * **Por que alguém paga**: Economiza de 20 a 40 horas de trabalho manual por mês de cada membro da equipe, viabiliza trabalho colaborativo e gera documentos prontos para submissão editorial sem retrabalho.

3. **Plano Enterprise (R$ 1.490 / mês ou contratos corporativos sob medida)**:
   * **Público**: Indústrias farmacêuticas, biotecnologia, CROs (*Contract Research Organizations*), grandes redes hospitalares e centros de pesquisa corporativa.
   * **Recursos**: Usuários e inquilinos ilimitados, cotas de hardware dedicadas, fila VIP analítica com Quality of Service (QoS de alta prioridade), Single Sign-On corporativo (SAML 2.0 & OIDC com Okta, Azure AD, Google e Keycloak), provisionamento automatizado de usuários via SCIM 2.0 (RFC 7643/7644), Trilha de Auditoria Criptográfica Imutável com encadeamento de hash SHA-256 (preparada para auditorias SOC 2 Tipo II e FDA 21 CFR Part 11), anonimização e mascaramento de PII (dados de pacientes sensíveis sob LGPD/HIPAA), SLA de disponibilidade de 99.9% e suporte técnico dedicado.

---

### 7. Métricas de Sucesso

| Métrica | Definição | Meta Inicial (6 meses) | Meta de Escala (12 meses) |
| :--- | :--- | :--- | :--- |
| **Cadastros Ativos** | Novos usuários registrados na plataforma. | 1.000 usuários cadastrados | 5.000 usuários |
| **Taxa de Ativação** | Usuários que sobem um dataset e geram a 1ª análise estatística nos primeiros 10 min. | $\ge 60\%$ de ativação | $\ge 75\%$ de ativação |
| **Assinantes Pagantes** | Clientes com assinatura ativa nos planos Team ou Enterprise. | 35 equipes pagantes | 150 equipes pagantes |
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
| **6. Fontes de Receita** | • Assinaturas mensais e anuais via Stripe:<br>&nbsp;&nbsp;- Plano Team: R$ 249/mês (ou R$ 199/mês anual).<br>&nbsp;&nbsp;- Plano Enterprise: R$ 1.490/mês.<br>• Contratos customizados para implantação em redes hospitalares e biobancos. |
| **7. Estrutura de Custos** | • Infraestrutura de nuvem (instâncias de computação para microsserviços, DuckDB e workers R/Python).<br>• Armazenamento de objetos (MinIO / AWS S3 para datasets e snapshots Parquet).<br>• Taxas de processamento de pagamentos do Stripe (gateway de faturamento).<br>• Custos de manutenção de domínio, certificados TLS e ferramentas de CI/CD. |
| **8. Métricas-Chave** | • Taxa de ativação de novos cadastros (1ª análise estatística em < 10 min).<br>• Número de relatórios e tabelas APA 7th exportadas por semana.<br>• MRR (Receita Recorrente Mensal) e Net Revenue Retention (NRR).<br>• Taxa de conversão de usuários Community para Team/Enterprise. |
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
| **Plano Premium (Stripe)** | **Microsserviço de Billing & Assinaturas Recorrentes** | Gestão automatizada dos planos Community, Team e Enterprise com Stripe Checkout, Webhooks e sincronização de cotas no banco. |
| **Swagger, CI/CD e Observabilidade** | **Documentação OpenAPI, Helm Charts Kubernetes & Testes** | Contratos canônicos OpenAPI (`@metastatistic/contracts`), esteira de testes automatizados (Vitest/Pytest), healthcheck centralizado no Gateway e deploy em containers. |

---

### 10. Backlog no GitHub (Roteiro das Próximas Entregas)

Para orientar a evolução nas atividades 10 (Negócio no Ar) e 11 (Assinatura com Stripe), o backlog estruturado contempla as seguintes *issues* fundamentais:

* **Issue #1 — Modelagem e Ingestão Analítica com DuckDB e Apache Arrow**
  * *Descrição*: Implementar o catálogo de datasets do Metastatistic com detecção automática de tipos estatísticos (contínuo, ordinal, nominal) e motor DuckDB em memória com streaming Arrow IPC de alta performance.
  * *Critérios de Aceitação*: Upload de CSV até 100 MB em menos de 2 segundos; visualização tabular paginada com edição de metadados.
* **Issue #2 — Controle de Acesso Baseado em Papéis (RBAC) e Isolamento Multi-Tenant**
  * *Descrição*: Estruturar o isolamento de dados por organização (`tenant_id`) com papéis de `admin`, `editor` e `viewer`, e roteamento de contexto no API Gateway.
  * *Critérios de Aceitação*: Usuário de um laboratório não enxerga dados de outro laboratório; permissões de edição respeitadas na API e na interface.
* **Issue #3 — Landing Page Comercial com Vitrine Interativa APA 7th**
  * *Descrição*: Desenvolver a página inicial pública da plataforma apresentando proposta de valor, tabela comparativa com concorrentes, vitrine de resultados no padrão APA e modal de autenticação integrado.
  * *Critérios de Aceitação*: Landing page responsiva com alternância de tema (Claro/Escuro), navegação fluida e botões de conversão ("Entrar" e "Criar Conta").
* **Issue #4 — Integração de Pagamentos Recorrentes com Stripe (Checkout & Portal)**
  * *Descrição*: Criar o microsserviço de faturamento (`billing-service`) integrado aos planos Community, Team e Enterprise, com criação de Checkout Sessions e tratamento de Webhooks.
  * *Critérios de Aceitação*: Transação no Stripe atualiza instantaneamente o plano da organização via webhook criptograficamente assinado; modal de planos permite troca de ciclo (mensal/anual).
* **Issue #5 — Motor Dual-Engine de Inferência Estatística Frequentista & Bayesiana**
  * *Descrição*: Implementar os motores analíticos (Engine Python SciPy e Engine R Worker isolado) com suporte a testes t, ANOVA e Fatores de Bayes com formatação editorial estrita.
  * *Critérios de Aceitação*: Execução de teste t independente gera tabela com $t$, graus de liberdade, $p$-valor, Cohen's d e nota de rodapé no padrão APA 7th.
* **Issue #6 — Trilha de Auditoria Criptográfica Imutável (FDA 21 CFR Part 11 & SOC 2)**
  * *Descrição*: Implementar registro de eventos encadeados por hash SHA-256 no microsserviço de auditoria com endpoint de verificação de adulteração.
  * *Critérios de Aceitação*: `GET /audit/verify` retorna status de integridade matemática e alerta se qualquer registro histórico for alterado.
  * *Status*: ✅ entregue em `services/audit-service` (extraído do `auth-tenant-service` em 2026-11-11); falta autenticação no serviço e entrega garantida dos eventos — ver `PLAN.md` §7.

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

**Principais pontos em aberto:** o gateway e os serviços confiam no header `X-Tenant-ID` e no `tenant_id` de um JWT cuja assinatura não é verificada — **qualquer cliente consegue ler dados de outro tenant** (verificado em teste, ver `PLAN.md` §7); autenticação no `audit-service`; entrega *best-effort* dos eventos de auditoria; dois logs de auditoria coexistindo (`apps/api` e `audit-service`); preços divergentes entre documentos e código.

---

## 🏛️ Topologia e Estrutura Técnica do Monorepo

O repositório está organizado como um monorepo moderno gerenciado via `pnpm-workspace.yaml`:

### Microsserviços e Backend
> **Processo `platform`:** no `docker-compose.yml`, `auth-tenant`, `billing`, `bi-report`, `export` e `audit` rodam **no mesmo processo** (`services/platform-service`, sob os prefixos `/_auth`, `/_billing`, `/_bi`, `/_export`, `/_audit`). Cada um continua sendo um app FastAPI independente (com Dockerfile e banco próprios; o Helm segue implantando um a um); juntos economizam ~230 MB de RAM. As portas citadas abaixo valem para a execução individual. No modo `platform` os bancos são `AUTH_`/`AUDIT_`/`BILLING_`/`BI_DATABASE_URL`.

* **`services/gateway`** (porta interna `8080`, exposta em `${GATEWAY_PORT:-8085}`): API Gateway e Edge Router assíncrono com resolução de inquilinos em cascata (subdomínio, cabeçalho `X-Tenant-ID`, JWT Bearer), proxy streaming via `httpx` e healthcheck agregador.
* **`services/auth-tenant-service`** (porta `8002`): IAM, governança de inquilinos (*tenants*), cotas estritas por assinatura (`community`, `team`, `enterprise`), RBAC com proteção ao *owner*, convites criptografados, SSO SAML 2.0 / OIDC e SCIM 2.0 (os eventos de auditoria são enviados ao `audit-service`).
* **`services/stat-orchestrator`** (porta `8003`): Orquestrador de computação analítica com fila assíncrona priorizada por QoS (clientes VIP furam fila), cache determinístico LRU por hash SHA-256 e roteador inteligente Dual-Engine.
* **`services/data-engine-service`** (porta `8004` / exposta `8014`): Motor de consulta analítica em DuckDB Sandbox confinada, streaming binário Apache Arrow IPC (`application/vnd.apache.arrow.stream`), anonimização e mascaramento de PII (LGPD/GDPR), conectores externos (SQLite, DuckDB, PostgreSQL, MySQL) e Data Prep.
* **`services/bi-report-service`** (porta `8005` / exposta `8015`): Microsserviço de relatórios colaborativos e dashboards em tempo real com WebSockets, versionamento e snapshots.
* **`services/export-service`** (porta `8006` / exposta `8016`): Gerador de relatórios multi-formato (HTML/PDF Paged Media APA 7th, LaTeX com booktabs, DOCX com estilos acadêmicos e Markdown GFM).
* **`services/billing-service`** (porta `8007` / exposta `8017`): Microsserviço de monetização e pagamentos Stripe: planos Community, Team e Enterprise, Checkout Sessions, Customer Portal, faturamento multi-tenant e webhooks com atualização automática de tier.
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
| `AUTH_ENABLED` / `COOKIE_SECURE` | `true` / `false` | sessão do app (`COOKIE_SECURE=true` atrás de HTTPS) |
| `JWT_SECRET_KEY` | chave de dev | assinatura dos JWT (`openssl rand -hex 32`) |
| `STRIPE_MOCK_MODE` | `true` | simula checkout e webhooks |
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

