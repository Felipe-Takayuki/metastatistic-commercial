# Fase 4 — mais análises (ANOVA, correlação, regressão, qui-quadrado) — CONCLUÍDA (falta só o commit)

**Última atualização: 2026-11-05 (sessão de conclusão).** Nada desta fase foi commitado ainda. A pilha ao vivo (`docker compose`, :8080) roda a versão **final** do worker e do front-end.

## 1. Resumo do estado

| Item | Estado |
|---|---|
| Salvar consulta SQL como dataset (`POST /datasets/from-query`) | ✅ 22 testes, sandbox |
| Worker com 4 módulos JASP | ✅ implantado (versão final de `engine.R` + `runner.R`) |
| ANOVA / Correlação / Regressão / Qui-quadrado | ✅ 124 valores conferidos contra o R puro |
| Front-end (formulários genéricos, seletor de análise, bloco de relatório) | ✅ 98 testes vitest |
| Integração permanente (`tests/test_analyses_integration.py`) | ✅ 10 testes, estáveis (3 rodadas seguidas: 10/10), inclui `test_endurance_*` (50 análises distintas, 6 em paralelo, nenhuma > 30 s) |
| API completa | ✅ 144 testes com `RUN_INTEGRATION=1` |
| e2e de navegador (`npm run e2e:analyses`) | ✅ SQL → "Salvar como dataset" → ANOVA/Correlação/Regressão/Qui-quadrado + bloco de ANOVA em relatório (recarregado); `e2e:all` = 3 suítes verdes |
| Travamento intermitente do motor | ⚠️ **não se reproduz**; causa raiz **não provada** (ver §4) |
| README/PLAN, commit | README ✅; commit ⏳ (aguardando o usuário) |

## 2. O que foi construído

### Backend (`apps/api`)
- `app/derive.py` + rota `POST /datasets/from-query {name, sql}`: grava o resultado de uma consulta como dataset novo (Parquet). Mesma validação de `/queries/run` (1 statement, só leitura, sem funções de tabela) e **mesmo sandbox do DuckDB**, com permissão de escrita para **um único arquivo** (o destino, gerado pelo servidor). Limites: 2 milhões de linhas (recusa em vez de truncar), 120 s; nunca deixa Parquet órfão.
- `datasets.py` refatorado: `describe_parquet()` e `register()` compartilhados entre CSV e consulta. `queries._sandbox(..., writable=[...])`.
- Config: `derived_dataset_max_rows`, `derived_dataset_timeout_s`.
- Uso típico (projeto `analise`): `SELECT ((row_number() OVER () - 1) % 4) + 1 AS bloco, * FROM <tabela>` → coluna `bloco` (ordinal, 4 níveis) para o delineamento em blocos casualizados.

### Worker R (`engines/r-worker`)
- `install-modules.sh`: instala na ordem de dependência `jaspTTests → jaspDescriptives → jaspAnova → jaspRegression`, `jaspFrequencies`. Pacotes que **só existem no GitHub** (`bstats`, `conting`, `flexplot`) entram antes por `git clone` + instalação local (conferido contra o repositório: são os únicos fora do CRAN/PPM). Imagem: **3,3 GB**.
- `engine.R`: registro fechado `ANALYSIS_MODULE` (análise → módulo), `init_jasp()` aquece **um módulo por vez e não derruba o motor se um falhar** (resultado por módulo em `/health → modules`), `valid_option_names` olha **todos** os QML do módulo (inclusive `common/`, onde ficam `modelTerms`/`postHocTerms`), `simplify_deep` (recursivo: `modelTerms = [{components:[…]}]`).
- **Remendo do `modelTerms`** (`restore_model_terms`/`install_bridge_patch`, só para `Anova`): ver §3.
- `runner.R`: prazo de aquecimento 420 s (agora são 4 módulos), `/health` expõe `modules`.
- `Dockerfile`: `setupJaspTools()` separado do aquecimento; `engine.R`/`runner.R` copiados **depois** (mexer neles não refaz o download).
- Custo medido: **partida/reinício do motor ~54–63 s** (antes ~17 s), **~560 MB em repouso** por motor. `docker-compose.yml`: `mem_limit` 1536m por worker.

### Front-end (`apps/web`)
- `lib/analyses.ts`: definições **declarativas** de 5 análises (t independente, ANOVA, Correlação, Regressão linear, Qui-quadrado) + motor genérico (`defaultState`, `resolveState`, `problems`, `toOptions`, `fromOptions`, `isComplete`). 31 testes em `analyses.test.ts`.
- `components/AnalysisForm.tsx` (formulário genérico controlado, estado efetivo gravado de volta), `AnalysisTab.tsx` (seletor + formulário + resultado), `report/AnalysisBlock.tsx` (escolhe análise e dataset; snapshot inclui análise+dataset+opções), `SqlTab.tsx` (**"Salvar como dataset…"**), `lib/blocks.ts` migrado. `TTestForm.tsx` e `lib/ttest.ts` removidos.
- **Decisão:** formulários **escritos à mão** (declarativos), não gerados do QML. O QML do JASP não é autocontido: o formulário de ANOVA se compõe de componentes de `common/classical/*` (construtor de termos, contrastes dinâmicos…), e gerar a partir dele exigiria reimplementar o motor de QML no navegador.

## 3. Descobertas importantes (guardar)

1. **`modelTerms` é repovoado pelo motor de QML.** `jaspTools::runAnalysis` passa as opções por `jaspSyntax::loadQmlAndParseOptionsStatus`; o controle de interação reconstrói `modelTerms` com **todas as interações** a partir de `fixedFactors`, ignorando o que se envia (testados 5 formatos de entrada; vale também para a interface oficial `jaspAnova::Anova(formula = y ~ A + B)`). Efeito: modelo aditivo impossível; no delineamento em blocos (1 observação por célula) o modelo satura e o JASP responde **"residual df = 0"**.
   **Remendo:** em `engine.R`, `parseOptionsThroughBridge` (função interna do jaspTools) é substituída via `assignInNamespace` por uma versão que, **depois** do replay, devolve ao `modelTerms` o que foi pedido, traduzindo nomes originais → codificados (`JASPColumn_D1_F1_n_Encoded`) pela posição em `fixedFactors`/`dependent`/… Aplica-se só a `Anova` (`PATCH_MODEL_TERMS`), preserva `name`/`title`, e se algo falhar segue sem remendo. **Frágil a atualizações do jaspTools/jaspSyntax** (módulos não têm versão fixada); os testes de integração (aditivo no fatorial replicado, DBC) são a guarda.
2. **Regressão linear:** `modelTerms` é uma lista de **modelos (blocos)**, não de termos (cada entrada = um modelo, com `components`, `name`, `title`). Sem `modelTerms` não sai nada. Um modelo com todos os preditores = `[{components:[…todos…], name:"model1", title:"Model 1"}]`. Corrigido em `REGRESSION_DEF.derive`.
3. Nomes de opção vieram dos testes oficiais dos módulos (`tests/testthat/test-*.R`). ANOVA: `dependent` (texto), `fixedFactors`, `modelTerms`, `postHocTerms` + `postHocCorrectionTukey|Bonferroni|Holm`, `effectSizeEstimates` (mestre) + `effectSize{Eta,PartialEta,Omega}Squared`, `homogeneityTests`, `qqPlot`, `descriptives`.
4. A análise lê os dados **sozinha** (pipeline nativo, `dataset = NULL` na função do módulo, colunas codificadas); o `data.frame` passado ao `runAnalysis` não é o que ela usa diretamente.
5. `fork()` do R com JASP carregado trava (Qt) — já documentado na Fase 2; o motor é processo filho iniciado do zero (callr).

## 4. Travamento intermitente do motor — situação

**Sintoma original** (sessão anterior): análises (sobretudo ANOVA) às vezes passavam de 60 s; o worker as matava (`504`) e recriava o motor (~50 s). Motor travado: estado `S`, CPU congelada, `wchan = sock_alloc_send_pskb` (escrita bloqueada em socket).

**O que foi feito agora:** com o worker implantado (`stdout = NULL`, **sem** dreno), rodadas de estresse pela API:
- 60 ANOVAs sequenciais com combinações distintas de opções (sem cache) e **481 em paralelo** (2 threads, 7 min): **0 travamentos, 0 reinícios** nos logs dos workers;
- depois, `test_endurance_*` (50 análises de 4 tipos, 6 em paralelo) e a suíte de integração 3×: tudo verde, ~30 s por rodada.

**Conclusão honesta:** o defeito **não se reproduziu** nesta configuração, mas **a causa original continua desconhecida** (a hipótese "buffer de stdout cheio sem leitura" nunca foi provada nem refutada de forma definitiva; a reprodução mínima não travava). O que mudou entre as observações e agora é, no mínimo, ambiental: na época havia `ENOSPC` do btrfs (metadados esgotados), disco a 93% e swap alto; hoje o disco está a 86%. Não dá para afirmar que está "corrigido".
- O `drain_output` do `runner.R` (escrito sobre a hipótese não provada) foi **removido**; o comentário em `spawn_engine()` registra isso.
- **Se voltar:** reproduzir e ler, por thread do motor, `/proc/<pid>/task/<tid>/{syscall,wchan,comm}` e `readlink /proc/<pid>/fd/<n>` (o 1º argumento de `syscall` é o fd) para saber **em qual socket** está preso. Amostrador usado: dispara ANOVAs com 6–10 flags combinadas por bits (evita cache) e despeja `/proc` do motor quando uma passa de 10 s. A recuperação automática (timeout → motor recriado) continua funcionando e `test_endurance_*` acusa o problema.

## 5. Ambiente da máquina (importante para quem retomar)

- **Disco raiz é btrfs, 93% usado.** Houve **`ENOSPC` real** (30/30 criações de arquivo falharam; a API ao vivo respondeu 500 em upload; `docker rmi` falhou com `no space left on device` no `meta.db` do containerd) embora `df` mostrasse ~17 GB livres — sintoma típico de **metadados do btrfs esgotados**. Voltou ao normal depois que removi imagens Docker obsoletas minhas (`metastatistic-r-base`, tag `:next`, ~3,5 GB). Confirmar com `sudo btrfs filesystem df /` e considerar `btrfs balance`/liberar espaço — **é decisão do usuário** (não tenho sudo).
- **Memória:** 7,7 GB; swap em uso 1–3,7 GB durante os testes. Cada worker ~550 MB; o contêiner de teste extra de 3 GB piorou. Evitar contêineres extras; validar na pilha ao vivo.
- `docker system df` e builds ficam muito lentos sob essa carga; **evitar builds grandes** (imagem do worker 3,3 GB; camadas só do `engine.R/runner.R` são baratas).
- Há outros processos pesados na máquina que não são meus (`npm install omniroute`, Metabase em :3000, bancos).

## 6. Estado da pilha ao vivo

- `web :8080` (bundle novo, com a correção do `modelTerms` da regressão e a transposição de tabelas), `api :8000`, `r-worker-1 :8001`, `r-worker-2`. Imagem `metastatistic-r-worker:spike` com o `engine.R` final (remendo do `modelTerms` só para `Anova`) e `runner.R` sem dreno. (Depois dessa implantação só um **comentário** do `runner.R` mudou; a próxima reconstrução o incorpora.)
- Dados do usuário **intactos**: dataset `dados_experimentais_limpos_jasp.csv.csv` e 2 relatórios "Análise de dados_experimentais_limpos_jasp.csv". Há ainda um **"Relatório sem título"** (1 bloco, criado 2026-11-05 18:26) que **não sei atribuir** — não foi apagado.
- Todos os datasets `e2e-*`/`tmp-*` de teste foram removidos.

## 7. Validação numérica (concluída)

Pela cadeia real (API → pool → worker → JASP), com o dataset do usuário (somente leitura) e referências do **R puro** (`aov`, `TukeyHSD`, `cor.test`, `lm`, `chisq.test`): **124 valores, 0 divergências** (tolerância relativa 1e-6; 1e-5 para p de Tukey/IC). E contra o **Python do projeto `analise`**: tratamento F = 2,5016680029…, p = 0,0489756426…; bloco F = 3,6719033594…, p = 0,0285662370… (aqui: 2,501668 / 0,048976 / 3,671903 / 0,028566; resíduo 21 gl; Tukey com 28 pares).
Para o repositório (sem dados reais): fixtures sintéticas determinísticas (`tests/fixtures/dbc_raw.csv`, `fatorial.csv`) e `r_reference.json` gerado por `make_reference.R` (comando de regeneração no cabeçalho do script).

## 8. Achados desta sessão (guardar)

1. **O bundle do `web` ao vivo estava desatualizado** (imagem de ~22 h): enviava `modelTerms` no formato ANOVA para a regressão (erro `options[['modelTerms']][[nModels]]`). Reconstruir e conferir (`grep model1` no bundle) — sempre rodar o e2e **depois** de reconstruir o `web`.
2. **Tabelas "de lado" do JASP** (`Chi-Squared Tests`, `Nominal`): uma linha com grupos de colunas `type[x]`, `value[x]`, `df[x]`… → agora transpostas em `lib/pivot.ts` (uma linha por teste; N inteiro). Só transpõe quando todas as colunas são `base[grupo]`, 1 linha, ≥ 2 grupos e cada grupo tem `type`.
3. O botão do relatório agora é "+ Análise" (antes "(teste t)").
4. `getByLabel("Análise", {exact:true})` não casa: o nome acessível do `<label>` inclui o texto das opções do `<select>`; usar regex.

## 9. Próximos passos sugeridos

1. Commitar a fase (aguardando o usuário).
2. Conferir o tema escuro das telas novas (as capturas desta sessão foram em tema claro).
3. Decidir o custo de reinício do motor (54–63 s): aquecer só os módulos mais usados.
4. Fixar versão/commit dos módulos JASP (o remendo do `modelTerms` depende disso).

## 10. Pendências conhecidas (além do travamento)

- Post hoc aplica-se a **todos** os fatores (inclusive bloco); não há seleção por fator.
- ~~ANCOVA, ANOVA de medidas repetidas, Kruskal-Wallis, modelos bayesianos~~ → **feitos na fase 6** (catálogo de 21 análises; ver `phase6-progress.md`). Seguem sem tela: contrastes personalizados, efeitos simples e mais de dois fatores intra-sujeito.
- ~~Descritivas sem tela própria~~ → feita na fase 6.1.
- Módulos JASP **sem versão fixada** (HEAD no momento do build): fixar tag/commit — o remendo do `modelTerms` depende disso.
- Aquecimento ~60 s (4 módulos) torna lenta a recuperação após timeout/queda.
- `valid_option_names` aceita qualquer nome declarado em QUALQUER arquivo do módulo (superconjunto): pega erros de digitação, não valida valores.
- Resultados do JASP continuam em inglês (padrão APA).
