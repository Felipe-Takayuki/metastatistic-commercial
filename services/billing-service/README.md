# MetaStatistic Commercial — Billing Service

Microsserviço de Gestão de Faturamento, Planos e Pagamentos Stripe para a plataforma MetaStatistic Commercial.

## Funcionalidades
- **Catálogo de Planos Comerciais**: Definição de planos Community (Free), Team ($49/mês ou $490/ano) e Enterprise ($299/mês ou $2990/ano).
- **Checkout Sessions Stripe**: Criação dinâmica de links de checkout para assinatura de planos via Stripe Checkout.
- **Customer Portal**: Redirecionamento seguro para gestão de formas de pagamento, histórico e cancelamentos via Stripe Customer Portal.
- **Processamento de Webhooks**:
  - `checkout.session.completed`: ativação instantânea da assinatura e notificação ao `auth-tenant-service` para atualização de tier e cotas.
  - `customer.subscription.updated`: sincronização de períodos e status.
  - `customer.subscription.deleted`: rebaixamento automático para o plano Community.
  - `invoice.payment_succeeded` & `invoice.payment_failed`: histórico de faturas e marcação de status past due.
- **Isolamento Multi-Tenant**: Faturas e assinaturas segregadas por `X-Tenant-ID`.
- **Modo Mock / Dev**: Suporte nativo para desenvolvimento e testes automatizados sem necessidade de credenciais de produção.

## Execução Local
```bash
uv run uvicorn app.main:app --port 8007 --reload
```

## Testes
```bash
uv run pytest
```
