# Metastatistic

Plataforma web de relatórios estatísticos (JASP + Metabase). Veja [PLAN.md](PLAN.md).

## Estrutura
- `apps/web` — interface (React + TypeScript + ECharts)
- `apps/api` — API FastAPI
- `engines/r-worker` — worker R: supervisor leve + motor JASP filho (tempo limite, recuperação automática)
- `packages/schemas` — contratos compartilhados (a definir)

## Fase 6 — catálogo estatístico (fatias 6.1 e 6.2)
Agora com **10 análises**: teste t (independente, pareado, uma amostra), ANOVA, ANCOVA, correlação, regressão linear e logística, qui-quadrado e estatísticas descritivas, todas conferidas contra o R puro: [docs/phase6-progress.md](docs/phase6-progress.md).

## Fase 5 — Dashboards (fatias 5.1 a 5.3; "Fase 4" do PLAN)
Grade arrastável/redimensionável de tiles (KPI, gráfico SQL, texto) com autosave e conflito por versão, **filtros globais** (`{{nome}}` no SQL) e **cross-filter** (clicar numa barra filtra os demais tiles) e **tiles de análise estatística** (JASP), em http://localhost:8080 → **Dashboards**. Drill-down, coleções e RBAC ficam para as próximas fatias: [docs/phase5-progress.md](docs/phase5-progress.md).

## Fase 4 — mais análises (concluída, ainda não commitada)
ANOVA (blocos casualizados, aditivo ou com interação, Tukey/Bonferroni/Holm), correlação, regressão linear e qui-quadrado, validados contra o R puro (124 valores, 0 divergências), formulários declarativos no front-end, bloco de análise nos relatórios e **"Salvar consulta como dataset"** (cria colunas derivadas, ex.: `bloco`). O travamento intermitente do motor **não se reproduziu** em ~540 análises distintas; há um teste de resistência como guarda. Detalhes, descobertas e pendências: [docs/phase4-progress.md](docs/phase4-progress.md).

## Fase 2 — execução robusta de análises (fatia 2.1)
Pool de 2 workers R, fila, tempo limite, cache e recuperação automática do motor: [docs/phase2-progress.md](docs/phase2-progress.md). Estado em tempo real: `GET /analyses/status`.

## Fase 3 — Relatórios (fatia 3.1)
Documentos com blocos de texto, gráfico e análise, com autosave e exportação em PDF: [docs/phase3-progress.md](docs/phase3-progress.md). Em http://localhost:8080 → **Relatórios**.

## Fase 1 — em andamento
**Interface:** http://localhost:8080 (após `docker compose up -d --build`). Testes: `cd apps/web && npm test` (unitários) e `npm run e2e:all` (navegador, 6 suítes; precisa da pilha no ar e de `pdftotext`).

Progresso, rotas e decisões: [docs/phase1-progress.md](docs/phase1-progress.md). Docs interativas da API em `http://localhost:8000/docs`.

```bash
curl -F file=@vendas.csv localhost:8000/datasets            # -> id, table_name, colunas
curl -X POST localhost:8000/queries/run -H 'content-type: application/json' \
     -d '{"sql":"SELECT regiao, sum(receita) FROM vendas GROUP BY 1"}'
```

## Fase 0 (spike) — concluída
Resultados e armadilhas: [docs/phase0-findings.md](docs/phase0-findings.md).

```bash
docker compose up -d --build        # worker leva ~15 s para aquecer; interface em http://localhost:8080
curl -s localhost:8000/health

# testes (venv local; o shim do uv no mise precisa de versão definida)
cd apps/api && python3 -m venv .venv && .venv/bin/pip install fastapi httpx pydantic-settings duckdb python-multipart sqlglot pytest pytest-asyncio respx
.venv/bin/pytest                                  # unitários
RUN_INTEGRATION=1 .venv/bin/pytest                # + integração contra o worker R, 2 workers (177)
```
