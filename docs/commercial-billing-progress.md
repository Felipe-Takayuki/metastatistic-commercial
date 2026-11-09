# Microsserviço de Billing e Pagamentos Stripe — MetaStatistic Commercial ✅ CONCLUÍDO (2026-11-09)

Módulo e microsserviço de monetização B2B SaaS, checkout, planos e gestão de faturamento Stripe para o **Metastatistic Commercial**. Permite autoatendimento de assinaturas, controle de cotas multi-inquilino (*multi-tenant*), sincronização bidirecional de webhooks com atualização automática de planos e histórico financeiro auditável.

---

## 1. O Que Foi Construído e Entregue

### 1.1 Microsserviço `services/billing-service`
Microsserviço de alta performance construído com FastAPI, SQLite persistente multi-tenant e SDK Stripe:
- **Catálogo Oficial de Planos Comerciais**:
  - `community`: Gratuito ($0/mês). 3 usuários, 10 datasets, 500 MB storage, engine JASP/R.
  - `team`: $49/mês ou $490/ano (2 meses gratuitos). 15 usuários, 100 datasets, 10 GB storage, conectores externos (PostgreSQL/MySQL), compartilhamento de relatórios e BI interativo.
  - `enterprise`: $299/mês ou $2990/ano (ou sob medida). Usuários ilimitados, datasets ilimitados, storage de alta capacidade, Dual-Engine (Python AGPL-free + R), SAML SSO, provisionamento SCIM 2.0 e Trilha de Auditoria Imutável (SOC 2 / FDA Part 11).
- **Checkout Sessions Stripe (`POST /billing/checkout`)**:
  - Criação dinâmica de links de checkout para assinatura de planos mensais ou anuais com provisionamento automático de Stripe Customer IDs.
  - Fallback automático para modo mock seguro e determinístico para ambientes de desenvolvimento, CI/CD e testes unitários.
- **Customer Portal Stripe (`POST /billing/portal`)**:
  - Emissão de URLs de autoatendimento para que os administradores dos clientes gerenciem cartões de crédito, troquem de plano ou façam cancelamentos no ambiente hospedado e seguro do Stripe.
- **Histórico Financeiro Multi-Tenant (`GET /billing/invoices`)**:
  - Registro segregado de faturas pagas e pendentes com valor devido, valor pago, moeda e links oficiais para faturas hospedadas (`hosted_invoice_url`).
- **Processamento de Webhooks Stripe com Verificação Criptográfica (`POST /billing/webhook`)**:
  - Validação estrita de assinatura via cabeçalho `Stripe-Signature` (rejeitando assinaturas inválidas com HTTP 400).
  - Trata os seguintes eventos do ciclo de vida:
    - `checkout.session.completed`: ativa a assinatura no banco de dados e notifica o `auth-tenant-service` via HTTP assíncrono para atualizar o tier do tenant imediatamente.
    - `customer.subscription.updated`: sincroniza datas de vigência, status da assinatura e mudanças de plano.
    - `customer.subscription.deleted`: marca assinatura como cancelada e rebaixa automaticamente o tenant para o plano `community`.
    - `invoice.payment_succeeded`: registra faturas quitadas no histórico contábil do tenant.
    - `invoice.payment_failed`: registra falhas de cobrança e marca a assinatura como `past_due`.

### 1.2 Atualização no `services/auth-tenant-service`
- **Atualização Dinâmica de Tier (`PATCH /tenants/{tenant_id}/tier`)**:
  - Endpoint dedicado para reajuste de plano (`community`, `team`, `enterprise`).
  - Atualização atômica no banco de dados com recálculo automático e imediato de cotas de usuários (`max_users`), armazenamento (`max_storage_mb`), limites de taxa e recursos habilitados.
  - Registro de auditoria imutável (`tenant.tier_updated`) na trilha criptográfica encadeada SHA-256.

### 1.3 Atualização no API Gateway (`services/gateway`)
- **Roteamento de Billing**:
  - `/api/v1/billing/*` reescrito para `/billing/*` e encaminhado com cabeçalhos de tenant para o `billing-service:8007`.
  - Rotas diretas `/billing/*` (checkout, portal, webhook, invoices, subscription, plans) roteadas nativamente.
- **Monitoramento de Saúde**:
  - Health check unificado (`GET /health`) agora monitora a disponibilidade do `billing_service`.

### 1.4 Orquestração e Infraestrutura
- **Docker Compose (`docker-compose.microservices.yml`)**:
  - Adicionado o container `billing-service` (porta `8017:8007`).
  - Criado volume persistente dedicado `billing_data`.
  - Atualizadas as dependências do `gateway` para incluir `billing-service`.
- **Helm Charts Kubernetes (`deploy/helm/metastatistic`)**:
  - Adicionado `templates/billing-deployment.yaml` e `templates/billing-service.yaml`.
  - Configurado `BILLING_SERVICE_URL` no `templates/configmap.yaml`.
  - Adicionado `billingService` no `values.yaml` (réplicas, recursos de CPU/memória, probes e HPA).
  - Suporte ao Horizontal Pod Autoscaler em `templates/hpa.yaml`.

---

## 2. Cobertura de Testes Automatizados

Foram executados e validados todos os testes com `uv run pytest` em todos os microsserviços do monorepo:

| Microsserviço | Testes Passando | Status |
|---|---|---|
| `services/billing-service` | 9/9 | 100% ✅ |
| `services/auth-tenant-service` | 12/12 | 100% ✅ |
| `services/gateway` | 11/11 | 100% ✅ |
| `services/bi-report-service` | 6/6 | 100% ✅ |
| `services/export-service` | 6/6 | 100% ✅ |
| `services/stat-orchestrator` | 13/13 | 100% ✅ |
| `services/data-engine-service` | 10/10 | 100% ✅ |
| **Total Global** | **67/67** | **100% ✅** |
