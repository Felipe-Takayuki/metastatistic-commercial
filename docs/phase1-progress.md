# Fase 1 — progresso (camada de dados)

## Fatia 1.1 — CSV → DuckDB/Parquet → SQL → análise por referência  ✅ (2026-11-04)

### API
| Rota | O que faz |
|---|---|
| `POST /datasets` (multipart `file`, `name?`) | Ingere CSV: DuckDB infere tipos lendo o arquivo todo, grava Parquet (zstd), registra metadados e nível de medida por coluna |
| `GET /datasets`, `GET /datasets/{id}` | Lista / detalha (colunas, tipos, `table_name` para SQL) |
| `PATCH /datasets/{id}` | Corrige o nível de medida (`nominal`/`ordinal`/`scale`) — define factor vs. numérico no R |
| `GET /datasets/{id}/preview` | Primeiras linhas |
| `DELETE /datasets/{id}` | Remove registro e Parquet |
| `POST /queries/run` | SQL somente leitura sobre os datasets (`SELECT … FROM <table_name>`) |
| `POST /analyses/run` | Agora recebe `dataset_id` (não mais dados inline) |

### Decisões
- **Parquet + volume compartilhado** em vez de JSON inline: o worker R lê só as colunas citadas nas
  opções (`nanoparquet::read_parquet(col_select=)`), com o volume montado **somente leitura**.
  - Desvio do plano: usei `nanoparquet` (sem dependências) em vez de `arrow` no R. Arrow só vale a
    pena se precisarmos de Flight/IPC; trocar é local ao `load_dataset()` em `runner.R`.
- **Nível de medida** inferido: texto/booleano/data → nominal; inteiro com ≤10 valores distintos →
  ordinal; demais numéricos → scale. Nominal/ordinal viram `factor` no R; scale vira `numeric`.
- **Metadados em SQLite** (`DATA_DIR/meta.db`) por enquanto; migrar para o Postgres do app na Fase 4
  junto com usuários/permissões.

### Segurança do SQL (3 camadas, todas testadas em `tests/test_queries.py`)
1. **sqlglot**: exatamente 1 statement, tipo consulta, sem funções de tabela (`read_csv()`, `range()`…).
2. **DuckDB travado**: `allowed_paths` = só os Parquets registrados, `enable_external_access=false`,
   `lock_configuration=true`. Cobre o que o parser não enxerga (ex.: `FROM "/etc/passwd"` é
   *replacement scan* de arquivo mas parece um identificador comum).
3. **Limites**: memória, nº de linhas (`truncated` na resposta) e timeout (`interrupt()` por timer).

Execução usa o SQL **original** (validado), não o regenerado pelo sqlglot; um `\n` antes do `)` do
wrapper impede que comentário `--` no fim engula o fechamento.

### Bugs achados pelos testes
- `SELECT …; -- comentário` falhava (o `;` não era o último caractere) → corte pelo último token.
- Opção desconhecida gerava tabela vazia em silêncio (Fase 0) → agora 422.

### Pendências conhecidas desta fatia
- `meta.db` fica no mesmo volume que o worker lê (só metadados, mas ideal é montar só `datasets/`).
- Todos os datasets ficam visíveis a todas as queries (sem usuários ainda → permissões na Fase 4).
- Metadados SQLite sem migrações/versionamento de schema.
- Colunas de data são `nominal` (refinar: tratar como temporal).
- Opções com listas aninhadas (ex.: `terms` de ANOVA) ainda não foram exercitadas contra o R.

## Fatia 1.5 — Frontend v1 ✅ (2026-11-04)

Interface em `apps/web` (Vite + React 19 + TypeScript 7). Docker: `http://localhost:8080` (nginx → `/api` → FastAPI). Dev: `npm run dev` em `apps/web` (porta 5173, proxy `/api`).

| Tela | O que faz |
|---|---|
| Barra lateral | Upload de CSV (clique/arrastar), lista, exclusão |
| **Dados** | Cartões de coluna (tipo, nº de valores distintos, nível de medida editável) + prévia de 100 linhas |
| **Consulta SQL** | Editor CodeMirror (Ctrl/⌘+Enter), chips de tabelas/colunas, resultado em **Tabela** ou **Gráfico** (barras, linhas, dispersão; até 3 séries) |
| **Análise estatística** | Teste t independente: variáveis, testes (Student/Welch/Mann-Whitney), descritivas, tamanho do efeito, pressupostos; resultado em tabelas **estilo APA** e gráfico descritivo |

### Decisões
- **Gráficos seguem a skill de dataviz**: paleta validada com o validador (3 primeiras posições, claro e escuro), barras ≤24 px com ponta de 4 px e base no zero, linhas 2 px, grade hairline, legenda com ≥2 séries, rótulo seletivo, tooltip com `textContent`, alvo de hover de 24 px na dispersão. A cor fica presa à série (remover uma não repinta as outras); máx. 3 séries (limite validado em todos os pares).
- **Tabela de dados sempre disponível** (alívio exigido pelo aviso de contraste do aqua no tema claro).
- **Formato numérico único**: ponto decimal nos dados, gráficos e tabelas APA (antes o gráfico usava vírgula e confundia).
- **Resultados do JASP**: o renderizador usa `.meta` para a ordem, o `format` do schema (`dp:3;p:.001`) para números e só aceita `em/sub/sup/b` no texto (sem `dangerouslySetInnerHTML`).
- **Gráficos do JASP** vêm como caminho de arquivo no disco do worker; o worker agora os **embute como data URI e apaga o arquivo** (senão o temp cresce a cada análise).
- Desvio do plano: **CodeMirror** no lugar de Monaco (bem menor); **CSS próprio com tokens** no lugar de Tailwind/shadcn. Ambos reversíveis.
- Bundle: ECharts/CodeMirror só carregam ao abrir a aba de SQL (carga inicial 76 KB gzip).

### Verificado
- Números exibidos conferidos contra o R puro (t, df, p, n, médias, DP, d de Cohen).
- `npm test` (24, lógica de formatação e gráficos) e `npm run e2e` (16 checks no navegador: fluxo completo, números iguais ao R, agrupamento inválido, **XSS** em nome de coluna/valor/tooltip, sem erros de console). O e2e cria e remove só os seus datasets.

### Bugs achados nesta fatia
- Variável de agrupamento padrão escolhia `data` (134 níveis) → agora o formulário mostra os níveis, prefere colunas de 2 níveis e bloqueia a execução com explicação.
- Erro de validação do JASP voltava como **500/502 com JSON cru** → agora **422** com mensagem limpa. (`n_distinct` passou a ser calculado para todas as colunas exceto ponto flutuante.)
- Legenda de linhas quase invisível; nota da tabela com `controle ,`; cabeçalho `v` indevido na tabela APA.
- O primeiro check de XSS do tooltip era falso positivo (lia a página, não o tooltip) → reescrito.

### Limitações conhecidas
- Saída do JASP em inglês (padrão APA); i18n fica para depois.
- Só o teste t independente tem formulário; pareado/uma amostra estão no worker mas sem tela.
- Sem salvar consultas/gráficos/resultados (isso é o editor de **relatórios**, Fase 3).
- Teclado e leitor de tela não foram testados a fundo nos gráficos (há `role="img"`, descrição e a aba Tabela).

## Próximas fatias da Fase 1
- 1.2 Upload de Excel (`.xlsx`) e SPSS (`.sav`, via `pyreadstat`).
- 1.3 Conexão com Postgres/MySQL (credenciais cifradas, usuário somente leitura, schema browser).
- 1.4 Query builder visual (filtro, agrupamento, agregação, ordenação, join) gerando SQL via sqlglot.
- 1.6 Mais visualizações (KPI, heatmap, área) e salvar consultas.
