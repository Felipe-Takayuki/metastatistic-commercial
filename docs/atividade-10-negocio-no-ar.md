# Atividade 10 — Seu negócio no ar

> Planejada para **06/11/2026** · entregue em **13/11/2026** (atrasada) · issue de entrega: ver [README §10](../README.md)
> Produto: **Metastatistic** — SaaS de BI e estatística inferencial com relatórios APA 7th.

A atividade pede a mesma stack do curso rodando o repositório do negócio: tabelas e API do negócio, papéis próprios, cada usuário vendo só os próprios dados, eventos de negócio no log, upload ligado ao domínio e landing page pública. Cada item abaixo diz **onde está no código**, **como conferir** e **o que ainda não está pronto**.

Os prints foram gerados por [`apps/web/e2e/evidencias.mjs`](../apps/web/e2e/evidencias.mjs) (Chromium headless contra a pilha rodando de verdade). Cada print traz, no rodapé da própria página, a hora em que foi tirado; [`evidencias/manifesto.json`](evidencias/manifesto.json) repete data, hora e URL de cada um.

## 1. Tabelas e API do negócio

O domínio deixou de ser "filmes" e passou a ser **datasets, análises, relatórios e organizações**.

| Tabela (SQLite) | Serviço | Para quê |
| :--- | :--- | :--- |
| `tenants`, `tenant_members`, `invitations` | `auth-tenant-service` | organizações (laboratórios), membros e papéis, convites |
| `users`, `sessions` | `apps/api` | contas, papel da plataforma e sessão por cookie |
| `datasets` (+ `tenant_id`, `dataset_acl`, `dataset_grants`, `dataset_rls`, `user_attributes`) | `apps/api` | catálogo de datasets, quem pode ler, segurança por linha |
| `reports`, `dashboards`, `collections`, `resources` | `apps/api` | relatórios e dashboards, dono de cada item |
| `audit` | `apps/api` | quem fez o quê |
| `subscriptions`, `invoices`, `tenant_customers`, `webhook_events` | `billing-service` | assinatura, faturas, cliente no Stripe, eventos recebidos |
| `audit_log` (cadeia SHA-256) | `audit-service` | trilha imutável de auditoria |

API pública (tudo passa pelo gateway em `/api/...`): `/datasets`, `/queries`, `/transforms`, `/analyses`, `/reports`, `/dashboards`, `/collections`, `/tenants`, `/billing/*`, `/auth/*`, `/audit`. A documentação interativa (OpenAPI) de cada serviço fica em `/docs`.

## 2. Papéis próprios

Dois níveis, definidos pelo negócio (pesquisa clínica), não pelo curso:

- **Plataforma** (`apps/api`): `viewer` (auditor/leitor), `editor` (pesquisador) e `admin` (gestor). O primeiro cadastro vira `admin`; os seguintes, `editor`. Cada rota exige o papel mínimo (`require_viewer/editor/admin`) e o acesso negado fica registrado.
- **Organização** (`auth-tenant-service`): `owner`, `admin`, `statistician`, `analyst`, `viewer`, com proteção do último dono.

Print: [`10-04-papeis-usuarios.png`](evidencias/10-04-papeis-usuarios.png).

## 3. Cada usuário vê só os próprios dados

- Dataset novo nasce **privado ao dono** (`DATASETS_PRIVATE_BY_DEFAULT`, ligado por padrão no `docker-compose.yml`). Outro usuário **não vê o dataset na lista e recebe 404** se tentar abrir (nem confirma que existe). O dono compartilha em "Acesso…"; o administrador vê tudo.
- Relatórios, dashboards e coleções têm dono (`resources.owner_id`): só o dono ou um administrador edita.
- Segurança por linha: uma coluna do dataset pode ser comparada com um atributo do usuário.
- Testes: `apps/api/tests/test_plan_limits.py::test_new_datasets_are_private_to_their_owner_when_configured`, `test_access.py`, `test_permissions.py`.

Prints: [`10-02-dados-do-usuario-camila.png`](evidencias/10-02-dados-do-usuario-camila.png) (a Camila vê o dataset que ela enviou) e [`10-03-dados-isolados-rafael.png`](evidencias/10-03-dados-isolados-rafael.png) (o Rafael, outro usuário, não vê nada; `GET /api/datasets` dele devolve `[]`).

> **Limitação conhecida:** a separação é **por usuário**. Os dados do `apps/api` ainda não são particionados **por organização** (a coluna `tenant_id` hoje só alimenta a contagem do limite do plano). Está no backlog: [#2](https://github.com/Felipe-Takayuki/metastatistic-commercial/issues/2).

## 4. Eventos de negócio no log

Duas camadas:

1. Tabela `audit` (e tela **Usuários > Auditoria**): cadastro, login (certo e errado), criação/exclusão/movimentação de datasets, relatórios e dashboards, mudança de acesso e acessos negados.
2. **Uma linha JSON por evento no log do processo** (`metastatistic.events`), no `apps/api` e no `billing-service`. Dá para filtrar com `docker compose logs api platform | grep '"event"'`.

Exemplo real (extraído do log da execução dos prints; arquivo completo em [`evidencias/logs-eventos-de-negocio.txt`](evidencias/logs-eventos-de-negocio.txt)):

```json
{"event": "user.register", "user": "camila", "detail": "novo cadastro (editor)"}
{"event": "dataset.create", "user": "camila", "detail": "ensaio_glicemia.csv (upload, 0.1 KB, plano Free)"}
{"event": "billing.checkout_created", "tenant": "8a4a2460-…", "plan": "pro", "session_id": "cs_test_0dc9…"}
{"event": "billing.checkout.session.completed", "tenant": "8a4a2460-…", "event_id": "evt_demo_checkout"}
{"event": "billing.webhook_duplicate", "event_id": "evt_demo_checkout", "type": "checkout.session.completed"}
```

Print da tela de auditoria: [`10-05-eventos-de-negocio.png`](evidencias/10-05-eventos-de-negocio.png).

## 5. Upload ligado ao domínio

O upload é o do negócio: o pesquisador envia um **CSV de dados do estudo** (`POST /datasets`). O arquivo é lido pelo DuckDB, os tipos são inferidos, vira **Parquet** com metadados (níveis de medida nominal/ordinal/escala) e fica disponível para SQL, transformações e análises estatísticas. O upload:

- respeita o **plano** da organização (limite de datasets e de tamanho por arquivo — ver [Atividade 11](atividade-11-saas-stripe.md));
- registra o dono e o evento de auditoria (`dataset.create ... plano Free`);
- nunca usa o nome do arquivo como caminho em disco.

A foto de perfil também é um upload de objeto (bucket Garage, compatível com S3), em `PUT /auth/me/avatar`.

## 6. Landing page pública

`apps/web/src/components/LandingPage.tsx`: proposta de valor, comparação com SPSS/JASP/Power BI, conformidade (LGPD, FDA 21 CFR Part 11, SOC 2), planos **Free (R$ 0)** e **Pro (R$ 249/mês)** e botões "Criar conta" e "Entrar". É a tela que quem não está logado vê em `/`.

Prints: [`10-01-landing-publica.png`](evidencias/10-01-landing-publica.png) e [`10-06-landing-planos.png`](evidencias/10-06-landing-planos.png).

## 7. Como reproduzir

```bash
cp .env.example .env            # em desenvolvimento tudo é opcional
docker compose up -d --build    # app em http://localhost:8085
# prints (com a pilha no ar e o banco vazio):
cd apps/web && E2E_URL=http://127.0.0.1:8085 EVIDENCE_DIR=../../docs/evidencias node e2e/evidencias.mjs
```

Testes: `cd apps/api && uv run pytest` (364 passam; 66 dependem do worker R e ficam pulados), `pnpm --filter @metastatistic/web test`. Resultado completo em [`evidencias/testes.txt`](evidencias/testes.txt).
