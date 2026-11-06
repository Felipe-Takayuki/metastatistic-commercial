# Fase 7 (projeto) — usuários, papéis e acesso ✅ CONCLUÍDA (7.1 a 7.5, 2026-11-06)

Corresponde a "Coleções, RBAC, permissões por fonte de dados e segurança por linha" da Fase 4 do PLAN.md e a "log de auditoria" da Fase 5.
7.1 autenticação e papéis · 7.2 dono e coleções · 7.3 leitura por dataset · 7.4 segurança por linha · 7.5 auditoria e expiração por inatividade.
**Estado final e limites conhecidos no fim deste arquivo.**

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

---

# Fatias 7.3, 7.4 e 7.5 — leitura por dataset, linhas por atributo, auditoria ✅

## 7.3 Acesso de leitura por dataset
- `PUT /datasets/{id}/access` (dono ou administrador): `restricted` + lista `user_ids`. Sem configuração = aberto a todos que entraram (como antes).
- Dataset restrito **some** para quem não pode lê-lo: fora da lista, 404 em detalhe/prévia/análise (nem confirma que existe) e **a tabela não existe no SQL dele** (o sandbox do DuckDB só cria as visões dos datasets legíveis).
- **Derivados herdam**: dataset salvo de uma consulta sobre fonte restrita fica restrito, com a **interseção** das listas das fontes (`permissions.inherit_for_derived`). Sem isso, um editor com acesso copiaria os dados para um dataset aberto.
- Relatórios/dashboards guardam SQL e rodam com as permissões de QUEM abre: quem não lê o dataset vê o erro "tabela não existe" no bloco, não os dados.

## 7.4 Segurança por linha
- Regra por dataset: **coluna ↔ atributo do usuário**. Atributos (`nome=valor1,valor2`) são definidos por administradores em Usuários → "Atributos". A pessoa vê só as linhas cuja coluna (comparada como texto) está entre os valores do atributo; **sem o atributo, nenhuma linha** (falha fechada). Administradores e o dono veem tudo.
- **SQL**: o sandbox abre, para quem tem filtro, um **Parquet já filtrado** (e o Parquet completo nem entra no `allowed_paths` dele): mesmo uma falha do analisador de SQL não alcança as linhas proibidas. Testado com UNION, `read_parquet`, string como tabela, `glob`, `duckdb_views()`.
- **Análises**: o motor R lê o Parquet pelo id. Para quem tem filtro, a API gera uma **cópia filtrada com id derivado** (`sha256(dataset|coluna|valores)`, em `datasets/` e registrada em `rls_views`) e passa esse id no lugar: **o worker R não mudou** (sem rebuild). O id da cópia também entra na chave do cache, então resultados de pessoas com filtros diferentes não se misturam. As cópias são apagadas quando a regra muda ou o dataset é excluído.
- **Derivados de dataset com regra de linhas** ficam restritos só ao dono/administradores (uma cópia completa não pode "abrir" as linhas filtradas); abrir depois é decisão explícita no diálogo de acesso.

## 7.5 Auditoria e expiração por inatividade
- Tabela `audit` (`GET /audit`, só administrador, paginação por `before_id`, filtro por `action`; aba **Auditoria** em Usuários, com negações e logins falhos destacados). Registra: primeiro acesso, login/logout, login falho e bloqueado (com o nome tentado, nunca a senha), troca de senha, criar/alterar/excluir usuário (papel, situação, atributos), criar/excluir datasets, relatórios, dashboards e coleções, mover, mudar acesso, e **acessos negados** (papel insuficiente, não é o dono, leitura recusada). **Não** registra salvamentos automáticos nem leituras/consultas. Falha ao gravar o log não derruba a operação.
- Sessão cai após `SESSION_IDLE_HOURS` (12) sem requisições (0 desliga); a última atividade é renovada no máximo 1×/min. O TTL absoluto (`SESSION_TTL_HOURS`, 168) continua valendo.

## Verificado
`pytest` 195 (+23: `test_permissions.py` 16 e `test_audit.py` 7), `vitest` 219 (+8), `tsc`/`vite build` limpos e `e2e:auth` estendido num navegador real (dono restringe e filtra; o editor com `regiao=Sul` vê 2 de 5 linhas na tabela e no SQL; leitor fora da lista não vê o dataset e leva 404; auditoria mostra mudança de acesso, login falho e acessos negados, sem senhas). O e2e passou, e nesta rodada o harness foi corrigido (ver abaixo).
**Não reexecutados** (Docker parado desde o início da fase): integração com o motor R (`RUN_INTEGRATION=1`) e `e2e:all`. Em especial, **a análise de um usuário com filtro de linhas contra o motor real não foi exercitada de ponta a ponta** (os testes provam que a API envia o id da cópia filtrada e que a cópia tem as linhas certas; o worker lê qualquer `<id32hex>.parquet` em `datasets/`, então deve funcionar, mas vale conferir com o Docker no ar).
Achado no caminho: `e2e/lib.mjs → finish()` chama `process.exit` dentro do `finally`, então **uma exceção no meio do teste saía como "Tudo certo"**. O `auth.mjs` agora captura e conta como falha; os outros 6 e2e têm o mesmo risco latente.

# Estado final da fase 7 e limites conhecidos

**Papéis** viewer ⊂ editor ⊂ admin · **dono** por recurso (editor mexe no que criou; admin em tudo) · **coleções** planas · **leitura por dataset** · **linhas por atributo** · **auditoria** · **sessões** com cookie HttpOnly, hash no banco, TTL e inatividade · senha scrypt · bloqueio por falhas.

Limites (decididos ou aceitos, não esquecidos):
- **Metadados vazam em datasets com filtro de linhas**: `n_rows` e `n_distinct` do dataset mostram a contagem COMPLETA, não a filtrada. Os valores das linhas não vazam. Ocultar exigiria recalcular por usuário.
- **Autenticação é opt-in** (`AUTH_ENABLED=false` por padrão): ligar é decisão de quem opera. Com ela desligada ninguém é auditado por nome e tudo é aberto.
- **Bloqueio por falhas é por usuário, em memória** (zera ao reiniciar o processo). Bloqueio por IP ficou de fora de propósito: atrás do nginx o IP visto é o do proxy e confiar em `X-Forwarded-For` permite forjar.
- Sem e-mail/recuperação de senha (o administrador redefine) e sem SSO (OIDC/SAML do PLAN): exigem provedor externo; ficam para quando houver um para integrar.
- Sem permissão por coleção (só organiza) e sem aninhamento; datasets não entram em coleções.
- Auditoria sem retenção/rotação (cresce sem limite) e sem exportação; a regra de linhas compara **uma coluna com um atributo** (sem expressões, sem várias colunas).
- As cópias filtradas ocupam disco (uma por combinação dataset × valores); são apagadas ao mudar a regra ou excluir o dataset, mas não por expiração.
- `/docs` e `/openapi.json` do FastAPI seguem públicos (só descrevem a API).
