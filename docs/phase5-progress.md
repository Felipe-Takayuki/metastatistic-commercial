# Fase 5 (projeto) — Dashboards, fatia 5.1 ✅ (2026-11-05)

Corresponde à **"Fase 4: Dashboards e colaboração" do PLAN.md** (a numeração do projeto andou à frente: a Fase 4 daqui foi "mais análises").
Esta fatia entrega a **grade arrastável**; cross-filter, drill-down, coleções, RBAC e segurança por linha continuam pendentes.
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
- **Cross-filter e drill-down** (clicar numa barra filtra os demais tiles) e **parâmetros/filtros globais** (`{{param}}` no SQL).
- Tile de **análise estatística** (hoje só KPI, gráfico e texto); tile de tabela.
- Exportar PDF do dashboard; coleções/pastas; RBAC e segurança por linha (exigem autenticação, que não existe).
- Em tela estreita não se reposicionam tiles. Sem desfazer/refazer. Sem tiles duplicados ("duplicar").
- Mesmo problema de largura em **Explorar** (`#/`) a 420 px (a barra lateral/tabelas estouram); não tratado aqui.
- Tema escuro dos dashboards não revisado visualmente.
