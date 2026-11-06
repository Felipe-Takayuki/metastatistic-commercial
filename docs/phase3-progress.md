# Fase 3 — Relatórios (fatia 3.1) ✅ (2026-11-04)

Relatório = documento salvo, composto por **blocos** reordenáveis. Interface em `#/reports` (http://localhost:8080).

## O que existe
| Peça | Detalhe |
|---|---|
| **Blocos** | **Texto** (Markdown seguro), **Gráfico** (SQL + barras/linhas/dispersão, com título), **Análise** (teste t independente: dataset + variáveis + opções) |
| **Edição** | Adicionar, mover ↑/↓, excluir (com confirmação), pré-visualização do Markdown, modo Editar/Visualizar |
| **Autosave** | Debounce de 0,8 s; indicador Salvo / Salvando / Erro (com "tentar de novo"); salva ao sair da página |
| **Conflito** | Bloqueio otimista por **versão** (`PUT` com `version`; 409 se outra aba salvou antes). A UI para de salvar e oferece "Recarregar a versão salva" |
| **PDF** | Botão **Exportar PDF**: força tema claro, imprime só o documento (CSS `@media print`), restaura o tema depois |
| **Exemplo** | "Criar exemplo com <dataset>" monta texto + gráfico + comparação + análise a partir das colunas |

API: `POST/GET /reports`, `GET/PUT/DELETE /reports/{id}` (lista devolve só resumo, sem blocos).
Limites validados no servidor: 100 blocos, 50 mil caracteres de Markdown, ids de bloco únicos `[A-Za-z0-9_-]{1,64}`, ≤3 séries por gráfico.

## Decisões
- **Os blocos guardam a *definição*, não o resultado** (SQL, opções, dataset). Ao abrir, tudo é reexecutado, então o relatório sempre reflete os dados atuais. Contrapartida: não há "foto" congelada (ver pendências).
- **Gráficos de relatório usam SVG** (vetor) em vez de canvas: no PDF o texto dos eixos ficava borrado e agora é texto de verdade (extraível). Acima de 3000 pontos volta ao canvas.
- **PDF pelo navegador** (sem servidor): simples e sem dependência nova. O servidor com Chromium headless entra na Fase 5 (e-mail agendado).
- **Markdown próprio**, sem biblioteca e sem `innerHTML`: o texto do relatório é conteúdo de usuário. `#` vira `h2` (o título do relatório é o único `h1`).
- **Cache de requisições** (`lib/remote.ts`) com chave por SQL/opções; é limpo quando os dados mudam (upload, exclusão, nível de medida).
- **`Saver` isolado** (`lib/saver.ts`): debounce, sem salvamentos concorrentes, edição durante um salvamento não se perde, conflito para tudo. Testado com tempo simulado.

## Verificado
- `pytest` 67 (API+integração), `vitest` 63, e2e Explorar 18 checks, e2e Relatórios 39 checks.
- O e2e de relatórios cobre: criar → editar os 3 blocos → reordenar → autosave → **recarregar e conferir persistência** → **PDF real inspecionado com `pdftotext`** (título, texto, tabela APA com os números do R, gráfico como texto vetorial; e **ausência** de menu/botões) → exportar com tema escuro ativo imprime claro e restaura → excluir bloco com confirmação → **conflito entre duas abas sem sobrescrever** → relatório inexistente → exclusão.
- Segurança: Markdown com `<script>`, `<img onerror>` e `[x](javascript:…)` nunca executa nem vira link; aparece como texto, na tela e no PDF.

## Bugs achados nesta fatia
- Trocar o dataset de um bloco de análise reexecutaria as opções **antigas** contra os dados novos (o snapshot não incluía o `dataset_id`) — corrigido antes de rodar.
- Rótulos do gráfico borrados no PDF (canvas) → SVG.
- Corrida no e2e Explorar (checava o cabeçalho antes da prévia carregar).
- **Intermitente, causa provável mas não confirmada**: uma execução do e2e travou com a análise presa no spinner (o gráfico SQL do mesmo relatório carregou normalmente). Coerente com o worker R atender **uma análise por vez, sem timeout interno**, enquanto outra análise estava em andamento. Não reproduziu em 6 execuções seguintes. Mitigação nesta fatia: a UI avisa após 8 s ("o motor executa uma análise por vez"). A correção de verdade é a fila + pool de workers da Fase 2.

## Pendências conhecidas
- Sem **parâmetros/filtros globais** do relatório (item central da Fase 3): hoje cada bloco tem o seu SQL/opções.
- Sem snapshot congelado dos resultados, **sem histórico de versões**, sem comentários, sem templates/temas, sem DOCX.
- Excluir um dataset deixa blocos de análise apontando para ele (a UI mostra "dataset removido"; não há aviso na exclusão).
- Gráfico no PDF não ocupa a largura toda da página (o SVG é medido no layout de tela).
- `Ctrl+P` direto, com a interface em tema escuro, imprime com cores escuras; use o botão **Exportar PDF**.
- Sem reordenar por arrastar (só ↑/↓) e sem inserir bloco no meio (só no fim).
- ~~Sem controle de acesso~~ → **resolvido na fase 7** (papéis, dono por relatório, coleções, auditoria; opt-in via `AUTH_ENABLED`). Ver `phase7-progress.md`.
