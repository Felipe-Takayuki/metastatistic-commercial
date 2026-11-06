# Fase Comercial 2 — IAM, Multi-Tenancy e API Gateway ✅ CONCLUÍDA (2026-11-06)

Segunda fase da evolução para a arquitetura de microsserviços do **Metastatistic Commercial**. Entrega o serviço dedicado de autenticação e governança multi-inquilino (`auth-tenant-service`), o roteamento inteligente no `gateway` com resolução de inquilinos em cascata, e a orquestração integrada via Docker Compose.

---

## 1. O Que Foi Construído e Entregue

### 1.1 Microsserviço de Identidade e Tenants (`services/auth-tenant-service`)
Operando de forma independente na porta `8002`, este microsserviço gerencia todo o ciclo de vida de inquilinos, membros, convites e controle de acesso baseado em papéis (RBAC):

- **Governança de Inquilinos & Cotas de Assinatura (`TIER_QUOTAS`)**:
  - `community`: até 3 usuários, 10 datasets, 500 MB de armazenamento, rate limit de 60 req/min.
  - `team`: até 15 usuários, 100 datasets, 10 GB de armazenamento, conectores adicionais, rate limit de 300 req/min.
  - `enterprise`: usuários e datasets ilimitados, motor estatístico proprietário (Engine B), SSO/SAML, logs de auditoria imutáveis, rate limit de 5.000 req/min.
  - Slugificação automática de nomes de organização com unicidade garantida.
- **Hierarquia de Papéis (RBAC) e Membros**:
  - Papéis tipados: `owner`, `admin`, `statistician`, `analyst`, `viewer`.
  - **Proteção ao Owner**: o proprietário original não pode ser removido do inquilino nem ter seu papel rebaixado, garantindo governança ininterrupta da conta.
- **Sistema Seguro de Convites**:
  - Geração de tokens de alta entropia via `secrets.token_urlsafe(32)`.
  - Data de expiração configurável (padrão de 7 dias).
  - Verificação de cotas no momento do disparo e do aceite do convite.
  - Endpoint `POST /auth/invitations/{token}/accept` que vincula ou registra o usuário diretamente no tenant destinatário.
- **Tokens JWT Compatíveis com RFC 7519**:
  - Assinatura criptográfica HS256 baseada em chave secreta compartilhada.
  - Claims incluídas: `sub` (ID do usuário), `tenant_id`, `role`, `tier`, `exp` e `iat`.
  - Mecanismos de validação e expiração com tratamento de erros explícito (`TokenExpiredError`, `InvalidTokenError`).

### 1.2 Microsserviço de API Gateway & Edge Router (`services/gateway`)
Ponto de entrada único da plataforma (porta `8080`), responsável por inspecionar, resolver o contexto de inquilino e rotear as requisições downstream:

- **Resolução de Tenant em Cascata (4 Níveis)**:
  1. **Cabeçalho explícito**: `X-Tenant-ID` presente na requisição HTTP.
  2. **Subdomínio da URL**: detecção de padrão `https://{tenant_slug}.metastatistic.com` (com exclusão estrita de subdomínios reservados do sistema como `api`, `web`, `gateway`, `admin`, `localhost`, etc.).
  3. **Token JWT Bearer**: extração da claim `tenant_id` do payload codificado em Base64URL contido no cabeçalho `Authorization: Bearer <token>`.
  4. **Fallback Seguro**: resolução transparente para o inquilino `default`.
- **Reverse Proxy Assíncrono com Streaming**:
  - Construído com `httpx.AsyncClient` com repasse de fluxos em chunks de dados (*streaming responses*).
  - Tabela de roteamento dinâmico:
    - `/api/v1/auth/*` e `/api/v1/tenants/*` ➔ `http://auth-tenant-service:8002`
    - `/api/v1/analyses/*` e `/api/v1/jobs/*` ➔ `http://stat-orchestrator:8003` (ou serviço analítico ativo)
    - `/api/v1/*` (`datasets`, `queries`, `reports`, `dashboards`, `transforms`) ➔ `http://api:8000`
  - Injeção forçada do cabeçalho canônico `X-Tenant-ID` nas requisições repassadas para os serviços downstream.
- **Healthcheck Agregador Unificado (`GET /health`)**:
  - O gateway consulta periodicamente os endpoints de saúde de todos os microsserviços downstream registrados (`auth-tenant-service`, `data-api`) e retorna um panorama consolidado do estado do sistema.

### 1.3 Orquestração Docker Compose (`docker-compose.microservices.yml`)
Configuração declarativa que orquestra os 5 componentes da arquitetura:
1. `gateway`: porta exposta `8080`.
2. `auth-tenant-service`: porta interna `8002`.
3. `api`: serviço de dados na porta interna `8000`.
4. `r-worker`: motor estatístico legado R na porta interna `6311`.
5. `web`: frontend Vite/React servido via Nginx.

---

## 2. Decisões Tomadas e Armadilhas Contornadas

1. **Filtragem de Headers Hop-by-Hop no Proxy**:
   - *Desafio*: Quando um proxy HTTP repassa cegamente todos os cabeçalhos da requisição cliente para o backend, cabeçalhos específicos de conexão como `Connection: keep-alive`, `Transfer-Encoding: chunked` e `Content-Length` podem conflitar com a pilha do servidor downstream, causando quedas de conexão ou respostas truncadas.
   - *Solução*: O gateway implementa um conjunto de exclusão `HOP_BY_HOP_HEADERS` que descarta esses cabeçalhos antes de reenviar a requisição via `httpx`.
2. **Inspeção de JWT no Gateway Sem Chave Secreta**:
   - *Desafio*: O gateway precisa descobrir rapidamente o `tenant_id` para rotear a requisição sem ter a responsabilidade de gerenciar as chaves privadas/secretas de assinatura de todos os tenants.
   - *Solução*: O resolver faz apenas a decodificação da segunda parte do JWT (payload) para extrair o `tenant_id`. A autenticação criptográfica completa e verificação de assinatura da requisição continuam sob responsabilidade estrita dos serviços receptores (`auth-tenant-service`).
3. **Mapeamento de Rotas com Prefixo `/api/v1`**:
   - *Desafio*: Os microsserviços de domínio definem suas rotas internamente na raiz (ex.: `/tenants/create`), enquanto clientes externos chamam `/api/v1/tenants/create`.
   - *Solução*: O mecanismo de reescrita do proxy (`determine_target_url`) traduz dinamicamente os prefixos de versão de API pública para os caminhos canônicos dos microsserviços downstream.

---

## 3. Verificação e Testes

A integridade do fluxo de autenticação e do roteamento foi validada de ponta a ponta:

| Componente | Testes | Status | Detalhes |
|---|---|---|---|
| `auth-tenant-service` | **6 testes** | ✅ PASSOU | Criação de tenants, limites de cotas de membros por tier, convites e expiração, geração/validação de tokens JWT. |
| `gateway` | **7 testes** | ✅ PASSOU | Resolução por cabeçalho, resolução por subdomínio, resolução por JWT Bearer, fallback padrão, proxy de rotas e healthcheck agregador. |
| `apps/api` | **330 testes** | ✅ PASSOU | Toda a suíte de dados mantém total interoperabilidade com o header `X-Tenant-ID`. |

---

## 4. Limitações Conhecidas

- O rate limiting por inquilino está definido nas cotas (`TIER_QUOTAS`), mas sua aplicação prática nessa fase ocorre em contadores locais; em clusters multirréplicas, o contador exigirá backend Redis distribuído.
- Autenticação corporativa via SAML 2.0 / SCIM (Enterprise) está planejada para ser conectada na Fase 6 de prontidão corporativa.
