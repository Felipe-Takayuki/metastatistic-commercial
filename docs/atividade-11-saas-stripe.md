# Atividade 11 — SaaS completo com Stripe

> Planejada para **13/11/2026** · entregue em **13/11/2026** · issue de entrega: ver [README §10](../README.md)

## Resumo do que a atividade pede e do que está pronto

| Requisito | Estado | Onde |
| :--- | :--- | :--- |
| Planos **Free** e **Pro**, assinatura recorrente **mensal em R$** | ✅ | `services/billing-service/billing_service/config.py` (`PLANS`) |
| Checkout de assinatura | ✅ no código e em modo simulado · ⏳ prints no Stripe real dependem das chaves de teste (ver abaixo) | `POST /billing/checkout` |
| Portal do cliente ("Gerenciar assinatura") | ✅ idem | `POST /billing/portal`, botão em `PricingModal.tsx` |
| Webhooks **validados** (assinatura) e **idempotentes** para os 4 eventos | ✅ | `billing_service/main.py` (`/billing/webhook`), tabela `webhook_events` |
| **Limites por plano barrados na API**, com mensagem que diz o limite e como liberar | ✅ datasets, tamanho do arquivo e usuários | `apps/api/app/plan_limits.py`, `auth_tenant_service/tenants.py` |
| **Painel admin**: usuários por plano, assinaturas ativas, MRR de teste, últimos eventos | ✅ | `GET /billing/admin/summary`, tela `#/admin` ("Assinaturas") |
| **Nenhuma chave no repositório** | ✅ | `.env` fora do git; `.env.example` só com nomes; ver §6 |
| Entrega por issue mencionando o professor, com prints | ✅ issue de entrega | — |

> **Honestidade sobre o Stripe:** os prints deste documento foram feitos com `STRIPE_MOCK_MODE=true` — checkout e webhooks **simulados** (o painel mostra o aviso "Stripe simulado (mock)"). O código para o Stripe de verdade existe e é o mesmo caminho (SDK `stripe`, verificação de assinatura `Stripe-Signature`), mas **não foi exercitado contra o Stripe real** porque não há chaves de teste neste ambiente. Passo a passo e critérios para fazer isso: issue [#3](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/3) e §5 abaixo.

## 1. Planos

| | Free | Pro |
| :--- | :--- | :--- |
| Preço | R$ 0 | **R$ 249,00 / mês** (recorrente, em BRL) |
| Usuários por organização | 3 | 15 |
| Datasets | 5 | 100 |
| Tamanho por arquivo | 10 MB | 200 MB |

Só há cobrança mensal (pedir `yearly` no checkout responde 400). Organização nova **sempre** nasce no Free: o gateway recusa (403) criar organização com tier pago, senão qualquer pessoa criaria uma Pro sem pagar. Internamente `free` = tier `community` e `pro` = tier `team`.

Print: [`11-01-planos-free-pro.png`](evidencias/11-01-planos-free-pro.png). Landing: [`10-06-landing-planos.png`](evidencias/10-06-landing-planos.png).

## 2. Fluxo da assinatura

```
Usuário (admin da organização) → "Assinar o Pro" → POST /api/billing/checkout
   → billing-service cria a Checkout Session (modo subscription, preço mensal em BRL) → redireciona para o Stripe
   → paga → Stripe chama POST /api/billing/webhook (checkout.session.completed)
   → billing-service valida a assinatura, grava a assinatura e faz PATCH /tenants/{id}/tier = team no auth-tenant-service
   → a próxima requisição já traz o plano novo (o gateway repassa tier e cotas à API)
```

Eventos tratados (todos exigem `Stripe-Signature` válido; sem ele, 400 e nada é gravado):

| Evento | Efeito |
| :--- | :--- |
| `checkout.session.completed` | cria/ativa a assinatura Pro e promove a organização |
| `customer.subscription.updated` | sincroniza status, período e "cancela no fim do ciclo" |
| `customer.subscription.deleted` | marca como cancelada e **rebaixa a organização para Free** |
| `invoice.payment_failed` | grava a fatura em aberto e marca a assinatura `past_due` (o plano segue enquanto o Stripe retenta) |
| *(extra)* `invoice.payment_succeeded` | grava a fatura paga no histórico |

**Idempotência.** O Stripe reentrega eventos. A chave é o `event.id`: a tabela `webhook_events` tem `event_id` como chave primária e o evento é "reivindicado" antes de qualquer efeito. A segunda entrega responde **200** (senão o Stripe continua tentando) com `duplicate: true` e **não repete o efeito** (testado: o `PATCH` de tier acontece uma vez só). Se o processamento falha, o evento é marcado `failed`, a resposta é 500 e a retentativa do Stripe consegue processar. Testes em `services/billing-service/tests/test_billing.py` (`test_webhook_is_idempotent_on_redelivery`, `test_failed_processing_can_be_retried`, `test_the_four_events_drive_the_subscription_lifecycle`).

Saída real da execução dos prints (reentrega do mesmo evento):

```json
{"received":true,"event_type":"checkout.session.completed","processed":true,"duplicate":true,"event_id":"evt_demo_checkout","detail":"Duplicate delivery of evt_demo_checkout: already processed"}
```

Print do plano Pro ativo, com o botão do portal: [`11-03-plano-pro-ativo.png`](evidencias/11-03-plano-pro-ativo.png).

## 3. Limites por plano, barrados na API

O gateway confere no `auth-tenant-service` se o usuário é membro da organização e repassa o **plano e as cotas verificados** em `X-Tenant-Tier`/`X-Tenant-Quotas` (os cabeçalhos que o cliente mandar são descartados). O `apps/api` aplica:

| Limite | Onde | Resposta |
| :--- | :--- | :--- |
| nº de datasets (upload, "salvar consulta", "salvar transformação") | `plan_limits.check_can_create_dataset` | **402** |
| tamanho do arquivo | `plan_limits.max_upload_bytes` | **402** |
| nº de usuários (convite e aceite) | `auth_tenant_service/tenants.py` | **403** |

Mensagem real devolvida pela API ao tentar o 6º dataset no Free:

> *Limite do plano Free: até 5 datasets por organização (você já tem 5). Faça upgrade para o plano Pro (menu Planos > Assinar o Pro) para liberar até 100 datasets e arquivos maiores.*

Print da interface mostrando exatamente isso: [`11-02-limite-do-plano-na-api.png`](evidencias/11-02-limite-do-plano-na-api.png). Testes: `apps/api/tests/test_plan_limits.py` (12 testes: mensagem, limite por organização, upgrade libera na hora, tamanho de arquivo, sem cabeçalho = limites do Free, cabeçalho adulterado cai no Free, sem autenticação = sem limite).

## 4. Painel admin

`GET /billing/admin/summary` e a tela **Assinaturas** (`#/admin`), só para o **administrador da plataforma** (o gateway devolve 403 para os demais — conferido na execução: usuária não admin recebeu `403`):

- usuários e organizações **por plano**;
- **assinaturas ativas** (e quantas estão em atraso);
- **MRR de teste** = soma das mensalidades das assinaturas ativas;
- **últimos eventos** do Stripe, com situação (`processed`, `ignored`, `failed`).

Print: [`11-04-painel-admin.png`](evidencias/11-04-painel-admin.png). No print há duas organizações Pro (uma com pagamento falho, simulado), por isso: 1 ativa, R$ 249,00 de MRR e 1 em atraso.

## 5. Como rodar com o Stripe de verdade (modo de teste)

1. No painel do Stripe (modo de teste), crie o produto **Pro** com preço **recorrente mensal em BRL, R$ 249,00**; copie o `price_...`.
2. `cp .env.example .env` e preencha **só no seu `.env`** (que está no `.gitignore`): `STRIPE_MOCK_MODE=false`, `STRIPE_SECRET_KEY=sk_test_...`, `STRIPE_WEBHOOK_SECRET=whsec_...`, `STRIPE_PRICE_ID=price_...`, `APP_URL=http://localhost:8085`.
3. Em desenvolvimento: `stripe listen --forward-to localhost:8085/api/billing/webhook` (o comando imprime o `whsec_...`). Em produção, cadastre o endpoint `<APP_URL>/api/billing/webhook` com os 4 eventos.
4. Assine com o cartão `4242 4242 4242 4242`, abra "Gerenciar assinatura" e cancele; confira o painel admin.

Com `ENVIRONMENT=production` o billing **recusa subir** com `STRIPE_MOCK_MODE=true` ou com as chaves de desenvolvimento.

## 6. Nenhuma chave no repositório

- `.env` está no `.gitignore`; o repositório só tem `.env.example` (nomes e instruções, sem valores).
- As chaves só entram por variável de ambiente (`docker-compose.yml`, Helm `secrets.*`). Os valores padrão de desenvolvimento (`sk_test_metastatistic_dev_key`) são marcadores públicos que o modo de produção rejeita.
- Verificação feita em 13/11/2026 no **histórico inteiro** e na árvore de trabalho (chaves `sk_`, `pk_`, `whsec_` e tokens do GitHub): **0 ocorrências**.

```bash
git grep -nIE "sk_(live|test)_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{20,}|pk_(live|test)_[A-Za-z0-9]{20,}" $(git rev-list --all) -- .
```

## 7. Testes

Resultado completo em [`evidencias/testes.txt`](evidencias/testes.txt): billing 43, auth-tenant 29, gateway 101, apps/api 364 (66 pulados que dependem do worker R), web 274. CI no GitHub Actions: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
