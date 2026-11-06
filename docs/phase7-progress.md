# Fase 7 (projeto) — usuários, papéis e acesso ✅ fatias 7.1 e 7.2 (2026-11-06)

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

---

# Fatia 7.2 — dono por recurso e coleções ✅

## Regra de quem altera
`viewer` só lê. `editor` altera/exclui **o que criou** e o que **não tem dono** (criado antes dos usuários ou com a autenticação desligada). `admin` altera tudo. Vale para datasets (medida, exclusão), relatórios e dashboards (salvar, mover, excluir). **Ler, consultar e analisar continua liberado a todos** (a restrição de leitura por fonte de dados é a 7.3). Ao excluir um usuário, o que ele criou passa a "sem dono".

## O que existe
- **Dono**: tabela `resources(kind, id, owner_id, collection_id)` à parte dos recursos (sem ALTER nas tabelas existentes; **recurso sem linha = legado**, sem dono, na raiz). Preenchida na criação (`access.claim`), apagada na exclusão. Os modelos de saída ganham `owner_name`, `collection_id` e `can_edit` (calculado para o usuário que pergunta); a interface esconde editar/excluir/mover quando `can_edit` é falso e a API devolve 403 mesmo assim (`security.can_modify`).
- **Coleções**: pastas **planas**, compartilhadas por relatórios e dashboards. `GET/POST /collections`, `PATCH/DELETE /collections/{id}` (criar: editor; renomear/excluir: criador ou admin; excluir **não apaga os itens**, eles voltam a "Sem coleção"). Mover: `PUT /reports|dashboards/{id}/collection` (não altera a `version`, então não gera conflito com quem está editando).
- **Interface**: nas listas de relatórios e dashboards, faixa de coleções (Todos / Sem coleção / cada coleção, com contagem; nova, renomear, excluir), "Mover para…" por item e "por <dono>" na linha. Relatório/dashboard de outra pessoa abre em modo leitura (sem "Editar").

## Verificado
`pytest` 172 (+8 em `tests/test_access.py`: dono registrado/anotado; só dono ou admin altera relatório, dashboard e dataset; CRUD e permissões de coleção; mover não muda versão e excluir coleção devolve à raiz; sem linha órfã; usuário excluído; item legado segue editável), `vitest` 211 (+5, `lib/collections.test.ts`), `tsc` limpo e `e2e:auth` estendido (31 checagens: coleção criada, movida e filtrada; outro editor vê "por <dono>", sem Excluir/Mover/Editar e com 403 na API; administrador altera e exclui coleção alheia sem apagar o relatório).
**Não reexecutados** (Docker parado): integração com o motor R e `e2e:all`. As listas de relatórios/dashboards ganharam a faixa de coleções (só aparece com ao menos um item ou coleção), então vale rodar o `e2e:all` quando o Docker voltar.

## Limites conhecidos
- Sem permissão por coleção (a coleção só organiza). Sem aninhamento.
- Datasets não entram em coleções (só têm dono).

## Próximas fatias (ainda abertas)
1. **Permissão por fonte de dados (7.3)**: quem pode LER cada dataset (hoje o SQL do usuário alcança todas as tabelas; validar as tabelas referenciadas com o `sqlglot` de `queries.py` e filtrar listagens, preview e análises).
2. **Segurança por linha** (atributos do usuário filtrando datasets).
3. Auditoria (quem fez o quê), expiração por inatividade, bloqueio por IP.
