# Fase 0 — resultados do spike (2026-11-04)

**Conclusão: a decisão arriscada do plano (usar módulos R do JASP como motor) é viável.**
Um teste t independente roda em container via `jaspTools`, é chamado pela API FastAPI e
reproduz o `stats::t.test` do R (Student e Welch) com a mesma precisão.

## O que funcionou
- `jaspTools::runAnalysis()` com `data.frame` + opções devolve uma lista (`results`, `status`, `state`).
  As tabelas trazem `data` + `schema` (inclui `format: "dp:3;p:.001"`) + `footnotes`, o suficiente
  para um renderizador APA no frontend.
- `jaspSyntax` (nova dependência do `jaspTools`) baixa uma lib nativa na instalação, mas **não exige
  display**: só precisa de `libegl1`/`libopengl0` no container.
- Resultado numérico idêntico ao R nativo (ver `apps/api/tests/test_integration.py`).

## Armadilhas encontradas
1. **`remotes::install_github` estoura o limite da API do GitHub** (60 req/h sem token) → o build
   instala `jaspGraphs → jaspBase → jaspSyntax → jaspTools` a partir de clones git (`install-deps.R`).
2. **Módulos precisam ser instalados no build, com dependências CRAN**; o `jaspTools` usa
   `install.packages(repos = NULL)`, que não resolve dependências.
3. **Custo de aquecimento**: 1ª análise de um processo R ≈ 9 s; seguintes ≈ 0,2 s. O worker deve ser
   um processo persistente. Startup do container ≈ 15 s (o `Installing jaspTTests from source`
   ainda ocorre uma vez por processo; aquecer no build não persistiu).
4. **`analysisOptions()` omite listas de variáveis vazias** (`dependent`), e opções desconhecidas eram
   aceitas em silêncio, gerando tabela **vazia** sem erro. O worker agora valida nomes (defaults ∪
   nomes do QML) e responde 422. Fase 2: substituir por JSON Schema gerado do QML.
5. Nomes de opção são os do QML (`student`, `welch`, `dependent`, `group`), não os da UI.

## Limitações do spike (viram trabalho das próximas fases)
- Dataset enviado inline no JSON (Fase 1: DuckDB + Arrow).
- Plumber é single-thread: uma análise por vez por container (Fase 2: fila Redis + pool de workers).
- Resposta é o `jaspResults` cru; falta o adaptador para `packages/schemas`.
- Só `jaspTTests` e 3 análises na allowlist; módulos sem versão fixada (fixar tag/commit).
- Sem timeout por análise dentro do worker (só `mem_limit`/`cpus` no compose).
- Licença: o worker usa código GPL/AGPL do JASP; decisão jurídica pendente (ver PLAN.md §2).
