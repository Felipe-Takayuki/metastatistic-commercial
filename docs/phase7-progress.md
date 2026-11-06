# Fase 7 (projeto) — usuários, papéis e acesso ✅ fatia 7.1 (2026-11-06)

Corresponde a "Coleções, RBAC e permissões" da Fase 4 do PLAN.md. A 7.1 entrega **autenticação e papéis globais**; coleções,
permissão por fonte de dados e segurança por linha ficam para as próximas fatias (abaixo).

## O que existe
| Peça | Detalhe |
|---|---|
| **Liga/desliga** | `AUTH_ENABLED` (padrão `false`: comportamento antigo, todos administradores, nenhum teste existente muda). `docker compose` repassa `AUTH_ENABLED` e `COOKIE_SECURE` do ambiente. |
| **Primeiro acesso** | Com a autenticação ligada e **zero usuários**, a interface mostra "Criar o administrador" (`POST /auth/setup`, só funciona enquanto não há usuário nenhum). |
| **Papéis** | `viewer` (lê; roda consultas e análises) ⊂ `editor` (cria/altera/exclui datasets, relatórios, dashboards) ⊂ `admin` (gerencia usuários). Imposto na API por dependências (`security.py`); a interface só esconde o que daria 403. |
| **Sessão** | Token aleatório em cookie `HttpOnly; SameSite=Lax` (`Secure` com `COOKIE_SECURE`); o banco guarda só o **SHA-256** do token. TTL `SESSION_TTL_HOURS` (168). Qualquer 401 da API devolve a interface ao login. |
| **Senhas** | `scrypt` da biblioteca padrão (sem dependência nova), sal por usuário, mínimo 8 caracteres. Login de usuário inexistente gasta o mesmo tempo e devolve a mesma mensagem. |
| **Força bruta** | 5 falhas seguidas por usuário → 429 por 60 s (em memória, por processo: zera ao reiniciar). |
| **Gestão** | Página `#/users` (só admin): criar, mudar papel, desativar/reativar, nova senha, excluir. Trocar a senha ou desativar **derruba as sessões** do usuário. O **último administrador ativo** não pode ser rebaixado, desativado nem excluído. Cada um troca a própria senha pelo botão "Senha" (exige a atual). |

API: `GET /auth/status` (público), `POST /auth/setup|login|logout|password`, `GET /auth/me`, `GET|POST /users`, `PATCH|DELETE /users/{id}`.

## Decisões
- **Opt-in, não obrigatório**: a plataforma ao vivo do usuário tem dados reais e nenhum usuário; ligar login por padrão o trancaria para fora. Para ligar: `AUTH_ENABLED=true docker compose up -d --no-deps api` (e reconstruir o `web`). O primeiro acesso cria a conta de admin; **os dados existentes continuam visíveis a todos** (ainda não há dono por recurso).
- **Cookie de sessão em vez de JWT**: revogação imediata (desativar/trocar senha) e nada sensível no cliente. `SameSite=Lax` cobre CSRF nas rotas que mudam estado (todas são POST/PUT/PATCH/DELETE).
- `/health`, `/auth/status`, `/auth/setup` e `/auth/login` são as únicas rotas sem sessão. `/docs` e `/openapi.json` seguem públicos (só descrevem a API).
- Sem e-mail/recuperação de senha: o admin redefine pela página de usuários.

## Verificado
`pytest` 164 (14 novos em `tests/test_auth.py`: tudo exige sessão; setup uma vez; login/logout; bloqueio por falhas; token não guardado em claro; expiração; matriz de papéis; desativar/trocar senha derruba sessão; último admin; senha própria), `vitest` 206 (`lib/auth.test.ts`), `tsc` e `vite build` limpos, e **`npm run e2e:auth`** (20 checagens num navegador real: primeiro acesso, criar usuários, leitor sem botões de edição e 403 na API, editor cria relatório, desativado cai no login). O e2e de auth exige pilha NOVA com `AUTH_ENABLED=true` (instruções no cabeçalho de `e2e/auth.mjs`) e **não entra no `e2e:all`**. Os testes de integração com o motor e os 6 e2e antigos não foram reexecutados nesta fatia (Docker parado); eles rodam com a autenticação desligada, que não mudou.

## Próximas fatias (ainda abertas)
1. **Dono por recurso + coleções** (pastas para relatórios/dashboards; `owner_id`, migração dos existentes para "sem dono"/admin).
2. **Permissão por fonte de dados**: quem pode ler cada dataset (hoje o SQL do usuário alcança todas as tabelas; precisa validar as tabelas referenciadas com o `sqlglot` já usado em `queries.py`).
3. **Segurança por linha** (atributos do usuário filtrando datasets).
4. Auditoria (quem fez o quê), expiração por inatividade, bloqueio por IP.
