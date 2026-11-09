# Plano de Negócio Executivo — Metastatistic Commercial

> **Atividade 9**: Fork e Plano de Negócio  
> **Disciplina**: Introdução à Computação em Nuvem / Arquiteturas Cloud para Big Data  
> **Docente**: Allan Siriani ([github.com/siriani](https://github.com/siriani))  
> **Data de Elaboração**: Novembro de 2026

---

## 1. Identificação do Produto e Posicionamento
* **Nome**: **Metastatistic** (*Metastatistic Commercial*)
* **Tagline**: *A plataforma SaaS que une a agilidade visual e preparação de dados sem código do Business Intelligence ao rigor estatístico inferencial e relatórios automatizados no padrão APA 7th para pesquisadores, bioestatísticos e equipes de P&D clínico.*

---

## 2. A Dor de Mercado
* **Segmento Afetado**: Bioestatísticos, epidemiologistas, coordenadores de ensaios clínicos, médicos pesquisadores e equipes analíticas de Pesquisa & Desenvolvimento (P&D).
* **Momento Crítico**: Ao realizar a transição entre dados brutos (bancos de prontuários, planilhas multicêntricas e ensaios laboratoriais) e a redação de relatórios técnicos regulatórios ou submissões a periódicos científicos internacionais de alto impacto (*peer-reviewed*).
* **Custo Atual da Dor**:
  * **Financeiro**: Licenciamento corporativo custoso de ferramentas legadas desktop (como IBM SPSS, que ultrapassa R$ 15.000/ano por estação de trabalho, ou pacotes SAS que exigem contratos de dezenas de milhares de dólares), além de contratação de consultorias estatísticas externas cobrando de R$ 200 a R$ 500 por hora.
  * **Tempo e Produtividade**: Gasto de 15 a 40 horas semanais por pesquisador em retrabalho puramente manual e repetitivo (limpeza de planilhas no Excel, colagem de dados entre softwares, recálculo de premissas estatísticas e formatação artesanal de tabelas no Microsoft Word para conformidade com o manual da APA 7ª Edição).
  * **Risco e Compliance**: Elevado risco de erro humano de transcrição (copy/paste), quebra de fórmulas, ausência de trilha de auditoria para fins de auditoria regulatória (**FDA 21 CFR Part 11**, ANVISA e **SOC 2**) e risco de retratação científica de artigos decorrente de falta de reprodutibilidade analítica.
* **Solução Atual (Status Quo)**:
  * Exportação de CSVs não higienizados;
  * Manipulação frágil em planilhas eletrônicas locais;
  * Processamento em programas desktop locais mono-usuário;
  * Redesenho manual de tabelas em editores de texto;
  * Ausência total de governança de acesso, mascaramento de PII (violando LGPD/HIPAA) e colaboração em tempo real.

---

## 3. Persona

### Dra. Camila Valente (36 anos)
* **Perfil**: Coordenadora de Pesquisa Clínica e Bioestatística em um Centro Oncológico de Referência e Professora Adjunta em Programa de Pós-Graduação em Ciências da Saúde.
* **Rotina**:
  * Gerencia simultaneamente 4 ensaios clínicos multicêntricos de imunoterapia.
  * Lida com coletas diárias de dados clínicos, dados genômicos e prontuários eletrônicos de centenas de pacientes.
  * Reúne-se semanalmente com comitês de ética, médicos investigadores e conselhos regulatórios, precisando gerar relatórios de eficácia e segurança atualizados em prazos curtos.
* **Objetivos**:
  * Carregar grandes bases de dados, aplicar filtros e transformações analíticas sem depender da equipe de TI, executar testes estatísticos paramétricos e bayesianos robustos e gerar tabelas e gráficos que atendam rigorosamente ao padrão editorial da APA 7th com 1 clique.
* **Frustrações**:
  * As ferramentas corporativas de BI (Power BI, Metabase) são ótimas para contagens e gráficos comerciais simples, mas não calculam estatística inferencial (como $t$ de Student/Welch, ANOVA com post-hoc corrigido, Fatores de Bayes $\text{BF}_{10}$, intervalos de confiança de 95% ou tamanhos de efeito de Cohen).
  * O software estatístico tradicional que usa (SPSS) é preso a um único desktop no laboratório, possui interface antiga, trava frequentemente com volumes maiores de dados e não permite que seus orientandos e pesquisadores remotos trabalhem juntos.
  * Perde finais de semana inteiros ajustando espaçamentos, linhas horizontais e notas de rodapé de tabelas no Word, temendo que uma célula alterada invalide semanas de trabalho e gere reprovação em auditorias.

---

## 4. Análise de Concorrentes e Alternativas

1. **IBM SPSS Statistics / SAS Desktop**
   * *O que faz*: Execução de testes estatísticos clássicos em ambiente desktop.
   * *O que faz mal*: Custo corporativo exorbitante, interface obsoleta dos anos 90, arquitetura local mono-usuário sem nuvem colaborativa, ausência de dashboards dinâmicos e dificuldade de integração com bancos analíticos modernos.
2. **Power BI / Tableau / Metabase**
   * *O que faz*: Visualização executiva de dados e Business Intelligence corporativo.
   * *O que faz mal*: Incapazes de realizar inferência científica. Não oferecem testes de hipóteses formais, não verificam premissas estatísticas (homocedasticidade, normalidade) e não produzem saídas em formato editorial APA 7th.
3. **Planilhas (Excel / Google Sheets) + Processo Manual**
   * *O que faz*: Solução improvisada comum para cálculos e gráficos rápidos.
   * *O que faz mal*: Zero governança, alto índice de erro humano por fórmulas corrompidas, lentidão extrema com milhares de linhas, formatação manual que drena centenas de horas e total descompasso com normas de segurança (LGPD/HIPAA/FDA).
4. **JASP Desktop / RStudio**
   * *O que faz*: Análise estatística de código aberto de alta qualidade com relatórios no padrão APA.
   * *O que faz mal*: Aplicações instaladas localmente para um único usuário por máquina. Não são organizadas em SaaS multi-inquilino, não oferecem cotas empresariais, não possuem painel web de dashboards nem mecanismo de faturamento integrado.

---

## 5. Proposta de Valor Única
> *"Transforme dados brutos em relatórios estatísticos e publicações científicas no padrão estrito APA 7th em minutos — combinando a facilidade visual e data prep do Metabase ao rigor inferencial do JASP, diretamente na nuvem e com conformidade regulatória para equipes."*

---

## 6. Modelo de Receita com Stripe

O modelo de receita opera sob assinatura recorrente mensal/anual no modelo SaaS Freemium através do **Stripe Billing**:

| Plano | Preço Mensal | Faturamento Anual | Limites e Recursos Principais |
| :--- | :--- | :--- | :--- |
| **Community** *(Free)* | **R$ 0** | R$ 0 | • 1 usuário individual<br>• Até 5 datasets de até 50 MB cada<br>• Análises frequenciais básicas (Descritivas, Teste t, Pearson)<br>• 1 dashboard ativo<br>• Relatórios com marca d'água<br>• Fila de processamento compartilhada |
| **Team** *(Pro)* | **R$ 249 / mês** | R$ 199 / mês *(R$ 2.388/ano)* | • Até 10 assentos com controle RBAC (Admin, Editor, Viewer)<br>• Datasets ilimitados de até 2 GB (DuckDB acelerado)<br>• Catálogo completo: ANOVA, ANCOVA, Testes Não-Paramétricos e Bayesiano ($\text{BF}_{10}$)<br>• Dashboards colaborativos ilimitados via WebSockets<br>• Exportação sem marca d'água em PDF APA 7th, DOCX e LaTeX<br>• Fila de processamento prioritária com cache inteligente |
| **Enterprise** *(Corporativo)* | **R$ 1.490 / mês** | Sob medida | • Usuários e inquilinos ilimitados<br>• Cotas de infraestrutura e computação dedicadas<br>• Fila VIP analítica com Quality of Service (QoS de alta prioridade)<br>• Single Sign-On corporativo (SSO SAML 2.0 & OIDC com Okta, Azure AD, Google)<br>• Provisionamento automático de contas via SCIM 2.0 (RFC 7643/7644)<br>• Trilha de Auditoria Criptográfica Imutável (SHA-256 Hash Chain - FDA 21 CFR Part 11 / SOC 2 Ready)<br>• Mascaramento e anonimização de PII (LGPD/HIPAA)<br>• SLA de disponibilidade de 99.9% e suporte prioritário |

---

## 7. Métricas de Sucesso

1. **Ativação Rápida (Time-to-Value)**: Mais de 60% dos novos usuários registrados executam sua primeira análise estatística com geração de tabela APA 7th em menos de 10 minutos após o cadastro.
2. **Assinantes Pagantes (Paid Teams)**: Conquistar 35 laboratórios/equipes ativas nos primeiros 6 meses e 150 equipes em 12 meses.
3. **Receita Recorrente Mensal (MRR)**: Atingir R$ 15.000 de MRR no 1º semestre de operação e R$ 65.000 ao fim do 1º ano.
4. **Retenção e Churn**: Churn mensal controlado abaixo de 2%, impulsionado pelo lock-in de produtividade dos relatórios históricos, dashboards salvos e dados regulatórios na nuvem.
5. **Eficiência de Aquisição (LTV/CAC)**: Relação superior a 4:1 decorrente do ciclo de viralidade orgânica acadêmica (pesquisadores citando o Metastatistic na seção metodológica de artigos científicos).

---

## 8. Lean Canvas

```
┌─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┬─────────────────────────┐
│ 1. PROBLEMA             │ 4. SOLUÇÃO              │ 3. PROPOSTA DE VALOR    │ 9. VANTAGEM INJUSTA     │ 2. SEGMENTOS            │
│ • Pacotes legados caros │ • Data prep visual e    │ A agilidade visual e    │ • Motor Dual-Engine     │ • Pesquisadores,        │
│   e locais (SPSS/SAS).  │   SQL com DuckDB.       │ preparação de dados     │   híbrido (SciPy + R)   │   bioestatísticos e     │
│ • BI corporativo sem    │ • Catálogo inferencial  │ do BI corporativo       │   sem violação AGPL.    │   coordenadores de      │
│   estatística inferente.│   frequentista e Bayes. │ com o rigor inferencial │ • Tipografia editorial  │   ensaios clínicos.     │
│ • Retrabalho manual no  │ • Exportação com 1      │ e relatórios no padrão  │   estrita e automatizada│ • Hospitais, centros    │
│   Excel e Word.         │   clique em APA 7th.    │ APA 7th em nuvem.       │   no padrão APA 7th.    │   oncológicos e CROs.   │
│                         ├─────────────────────────┤                         ├─────────────────────────┤                         │
│                         │ 8. MÉTRICAS-CHAVE       │                         │ 5. CANAIS               │                         │
│                         │ • Taxa de ativação (<10m)│                         │ • Citações em artigos.  │                         │
│                         │ • Relatórios exportados.│                         │ • Congressos de saúde.  │                         │
│                         │ • MRR e Churn (<2%).    │                         │ • Parcerias acadêmicas. │                         │
├─────────────────────────┴─────────────────────────┴─────────────────────────┴─────────────────────────┴─────────────────────────┤
│ 7. ESTRUTURA DE CUSTOS                                                      │ 6. FONTES DE RECEITA                              │
│ • Servidores de computação em nuvem (FastAPI + DuckDB + R Workers).         │ • Assinaturas Stripe (Team a R$ 249/mês;          │
│ • Armazenamento de objetos (MinIO / S3) para datasets e relatórios.         │   Enterprise a R$ 1.490/mês).                     │
│ • Taxas de processamento financeiro do Stripe (gateway).                    │ • Contratos de implantação dedicada corporativa.  │
└─────────────────────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────┘
```

---

## 9. Mapa de Reaproveitamento da Infraestrutura

| Componente Construído | Papel no SaaS Metastatistic | Valor Entregue ao Negócio |
| :--- | :--- | :--- |
| **Catálogo de Filmes (TMDB)** | **Catálogo de Datasets e Análises Estatísticas** | Gestão de dados tabulares, esquema de colunas, tipagem estatística e catálogo de testes inferenciais. |
| **Login + RBAC** | **IAM Multi-Tenant, SSO Corporativo e SCIM 2.0** | Isolamento por organização com papéis de `admin`, `editor` e `viewer`, e login corporativo via Okta/Azure AD. |
| **Logs e Auditoria (Redis)** | **Trilha de Auditoria Criptográfica Imutável (SHA-256)** | Rastreamento imutável de eventos analíticos para conformidade regulatória com **FDA 21 CFR Part 11**. |
| **Upload e Perfil (MinIO/S3)** | **Repositório de Dados Brutos e Snapshots** | Armazenamento seguro de grandes arquivos CSV, datasets Parquet e snapshots versionados de relatórios. |
| **Plano Premium (Stripe)** | **Microsserviço de Billing & Assinaturas** | Cobrança recorrente dos planos Team e Enterprise com Checkout, Customer Portal e sincronização por webhook. |
| **Swagger, CI/CD e Observabilidade** | **OpenAPI, Helm Kubernetes & Testes** | Contratos canônicos de API, orquestração Kubernetes empresarial e esteira automatizada com mais de 260 testes. |

---

## 10. Backlog de Entregas (GitHub Issues)

1. **Issue #1 — Catálogo de Dados Analíticos e Ingestão com DuckDB**: Modelagem de dados, ingestão de CSV/Parquet e cálculo de metadados estatísticos.
2. **Issue #2 — Multi-Tenancy e RBAC com Cotas por Organização**: Segregação de inquilinos, convites criptografados e controle de permissões.
3. **Issue #3 — Landing Page Pública com Vitrine Interativa APA 7th**: Interface pública para conversão de novos usuários com alternância de tema e demonstração de resultados.
4. **Issue #4 — Faturamento Recorrente com Stripe**: Integração do `billing-service` com Checkout Sessions, Webhooks e gestão de planos.
5. **Issue #5 — Motor Analítico Dual-Engine (SciPy + R)**: Execução assíncrona com fila priorizada de testes paramétricos e Bayesianos com tabelas editoriais APA 7th.
6. **Issue #6 — Trilha de Auditoria com Hash Chain SHA-256**: Implementação de cadeia de custódia matemática para verificação de adulteração em tempo real.

---
> Acompanhamento: Professor **Allan Siriani** ([github.com/siriani](https://github.com/siriani))
