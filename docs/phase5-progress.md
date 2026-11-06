# Fase 5 (projeto) — Dashboards: fatias 5.1, 5.2 e 5.3 ✅ (2026-11-05)

Corresponde à **"Fase 4: Dashboards e colaboração" do PLAN.md** (a numeração do projeto andou à frente: a Fase 4 daqui foi "mais análises").
A **5.1** entrega a grade arrastável; a **5.2** (seção final) entrega filtros globais e cross-filter. Drill-down, coleções, RBAC e segurança por linha continuam pendentes.
Interface: http://localhost:8080 → **Dashboards** (`#/dashboards`).

## O que existe
| Peça | Detalhe |
|---|---|
| **Tiles** | **KPI** (1ª coluna da 1ª linha do SQL; casas decimais, prefixo, sufixo, formato pt-BR), **Gráfico** (SQL + barras/linhas/dispersão, mesmo editor dos relatórios), **Texto** (Markdown seguro) |
| **Grade** | 12 colunas (`react-grid-layout` 2.3.0); arrastar pelo cabeçalho, redimensionar pelo canto, compactação vertical; só no modo **Editar** (leitura = grade travada) |
| **Edição de conteúdo** | Botão ✎ do tile abre um diálogo (Esc/Concluir fecha); ✕ exclui com confirmação |
| **Autosave + conflito** | Reaproveita o `Saver` dos relatórios: debounce 0,8 s, `PUT` com `version`, 409 → para de salvar e oferece "Recarregar a versão salva" |
| **Tela estreita** | Abaixo de 720 px os tiles empilham em coluna única (ordem de leitura); posições só se editam em telas largas |

API: `POST/GET /dashboards`, `GET/PUT/DELETE /dashboards/{id}` (a lista devolve só o resumo). Validação no servidor: grade de 12 colunas (`x + w ≤ 12`, `h ≤ 40`), até 60 tiles, ids únicos, `decimals` 0–6, tile sem `layout` = 422.

## Decisões
- **Tiles guardam a *definição* (SQL), não o resultado**, como os blocos de relatório: ao abrir, tudo reexecuta contra os dados atuais.
- **Biblioteca de grade em vez de implementação própria**: arrastar/redimensionar com colisão e compactação é fácil de errar. A v2 é TypeScript nativo e funciona com React 19.
- **`applyLayout` devolve a mesma referência quando nada mudou** e o `onLayoutChange` é ignorado fora do modo edição: a grade dispara o evento ao montar (normaliza/compacta), e isso NÃO pode marcar o dashboard como alterado nem reescrever posições salvas (há check de e2e).
- **SQL do tile em edição fica congelado até fechar o diálogo.** Sem isso o tile de fundo reexecutava a consulta a cada tecla (SQL pela metade → dezenas de 422 e carga inútil no banco). Achado pelo e2e.
- Persistência em SQLite (tabela `dashboards`), mesmo modelo de `reports`. `dashboards.py` espelha `reports.py` de propósito (≈80 linhas); se aparecer um terceiro tipo de documento, vale extrair um repositório genérico.

## Verificado
- `pytest` 158 (14 novos de dashboards), `vitest` 106 (8 novos: `lib/dashboard.ts`), e2e `dashboards.mjs` 24 checks; `e2e:all` = 4 suítes verdes.
- O e2e cobre: criar → KPI (valor igual à média calculada do CSV, formato pt-BR) → gráfico → texto com XSS (aparece como texto) → **arrastar e redimensionar com o mouse e conferir no servidor** → grade sem sobreposição → recarregar (modo leitura, mesmos valores) → leitura não move nem salva nada → tela de 420 px empilhada e sem rolagem horizontal → excluir tile com confirmação → **conflito entre duas abas** → excluir dashboard.

## Bugs achados nesta fatia
- Reexecução da consulta a cada tecla no editor de tile (ver acima).
- A barra superior estourava a largura em telas estreitas (já existia; o 3º link a agravou): agora a navegação desce para a 2ª linha (`max-width: 640px`).

## Pendências
- **Drill-down** (clicar numa barra abre o detalhe).
- Tile de **tabela** (resultado de SQL).
- Exportar PDF do dashboard. ~~Coleções/pastas, RBAC e segurança por linha~~ → **feitos na fase 7** (coleções planas compartilhadas com relatórios; papéis; dono por item; linhas por atributo no nível do dataset). Ver `phase7-progress.md`.
- Em tela estreita não se reposicionam tiles. Sem desfazer/refazer. Sem tiles duplicados ("duplicar").
- Mesmo problema de largura em **Explorar** (`#/`) a 420 px (a barra lateral/tabelas estouram); não tratado aqui.
- Tema escuro dos dashboards não revisado visualmente.

---

# Fatia 5.2 — filtros globais e cross-filter ✅

## O que existe
| Peça | Detalhe |
|---|---|
| **Filtros** | Até 10 por dashboard, tipos **texto / número / data**, com nome (identificador), rótulo e valor inicial. Editor em "Filtros do dashboard" (modo Editar); barra de filtros acima da grade (também em leitura) com "Limpar filtros" |
| **Uso no SQL** | `{{nome}}` em qualquer SQL de tile. Filtro vazio vale `NULL`: `WHERE ({{grupo}} IS NULL OR "group" = {{grupo}})` |
| **Cross-filter** | Cada gráfico pode "definir o filtro X ao clicar numa barra ou ponto"; clicar de novo na mesma categoria limpa. Todos os tiles que usam `{{X}}` recarregam |
| **Persistência** | As **definições** (e o filtro de clique de cada gráfico) são salvas com o dashboard; os **valores** não (cada visitante filtra do seu jeito; recarregar volta ao valor inicial) |

## Decisões e segurança
- **A substituição é feita no cliente com literais escapados** (`lib/params.ts`) e o servidor continua vendo SQL comum, validado pelo mesmo sandbox de leitura. Texto: aspas simples duplicadas; número: só `-?\d+([.,]\d+)?`; data: `AAAA-MM-DD` existente (`DATE '…'`); vazio: `NULL`. Nada digitado vira SQL, e o valor **não é re-substituído** (digitar `{{outro}}` fica como texto). Testes unitários incluem tentativas de injeção; o e2e digita `x' OR '1'='1` e vê KPI 0 sem erro.
- Filtro desconhecido ou valor inválido: o tile mostra o erro e **não consulta**.
- O servidor valida: nomes `[A-Za-z_][A-Za-z0-9_]{0,39}` únicos, tipos, máx. 10, e `click_param` só pode apontar para filtro declarado (422 se não).
- Lista de filtros com problema (nome vazio/repetido) **não é salva** até corrigir (a UI avisa), em vez de entrar em laço de erro 422.
- Remover um filtro limpa o `click_param` dos gráficos que o usavam. **Renomear não reescreve os SQLs** (avisado na tela).
- **Migração**: bancos criados antes da 5.2 ganham a coluna `filters_json` automaticamente (`db.connect`; teste com banco antigo).
- O editor de KPI/gráfico aplica os filtros atuais ao SQL de prévia, então o que se vê no diálogo é o que o tile mostrará.

## Verificado
- `pytest` 167 (9 novos), `vitest` 118 (12 novos, `lib/params.ts`), e2e `dashboard-filters.mjs` (22 checks); `e2e:all` = 5 suítes verdes.
- O e2e cobre: definir filtro (salvo com nome/rótulo/tipo), **nome repetido avisa e não envia**, KPI com `{{grupo}}` (valor inicial vazio = todas as linhas), filtrar digitando (a, b, inexistente, aspas), limpar, **clicar na barra filtra o KPI e clicar de novo limpa**, definições persistem e valores não, leitura não altera o servidor.

## Pendências desta fatia
- Filtro de **lista de valores** (select com os valores distintos da coluna) e de **intervalo de datas**; hoje o texto é digitado.
- Os valores dos filtros não vão na URL (não dá para compartilhar um dashboard já filtrado).
- Cross-filter só em gráficos de **barras/linhas/pontos pela categoria do eixo X** (não por série). Sem destaque visual da barra selecionada.
- Placeholders dentro de literais/comentários do SQL também são substituídos (comportamento simples e previsível, mas atenção ao escrever).

---

# Fatia 5.3 — tile de análise estatística ✅

Liga o BI ao motor JASP: um dashboard pode misturar KPIs, gráficos SQL, textos e **análises** (as 5 do catálogo: teste t, ANOVA, correlação, regressão linear, qui-quadrado).

## O que existe
- Botão **+ Análise**; o diálogo reaproveita o `AnalysisBlockEditor` dos relatórios (dataset, análise, variáveis, opções, "Executar análise") e fica mais largo para caber formulário + resultado.
- O tile mostra o resultado do JASP (tabelas APA/gráficos) com rolagem interna; o cabeçalho traz o nome da análise. Em modo leitura, sem botões.
- Guarda a **definição** (`analysis`, `dataset_id`, `options`), nunca o resultado: ao abrir, reexecuta (com o cache da API: abrir de novo é instantâneo).
- Análise incompleta/desconhecida mostra o aviso dos relatórios. **Dataset excluído** agora mostra "O dataset desta análise foi excluído. Abra o modo de edição e escolha outro." (antes aparecia `dataset not found: <id>`; a correção vale também para relatórios).

## Decisões
- `AnalysisTile` herda `AnalysisBlock` (mesmo contrato dos relatórios) + `layout`: nenhuma lógica nova de análise.
- **Filtros do dashboard NÃO se aplicam às análises** (elas leem o dataset inteiro, sem SQL). O diálogo avisa. Para analisar um recorte, a saída é "Salvar consulta como dataset" (Fase 4) e analisar o dataset derivado.

## Verificado
- `pytest` 169 (2 novos), `vitest` 120 (2 novos), e2e `dashboard-analysis.mjs` (10 checks com o motor R real); `e2e:all` = 6 suítes verdes.
- O e2e cobre: diálogo com padrões do teste t, resultado igual ao R (t=-2.628, gl=78, p=.010) no diálogo e no tile, servidor guarda só a definição, convivência com KPI sem sobreposição, recarregar reexecuta, leitura sem botões, dataset excluído → erro legível.

## Pendências desta fatia
- Filtros que recortem a análise (exigiria materializar o recorte como dataset temporário).
- Cada análise ocupa um motor por vez; um dashboard com muitas análises serializa no pool (a fila e o aviso "ainda calculando" existem, mas só no bloco de relatório; no tile a espera é só o spinner).
