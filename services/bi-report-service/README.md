# MetaStatistic BI & Report Service (`bi-report-service`)

Microsserviço de Business Intelligence e Relatórios Colaborativos da plataforma MetaStatistic.

## Funcionalidades
- CRUD completo de Relatórios analíticos com suporte a blocos modulares (texto, cabeçalhos, gráficos, tabelas APA 7th, equações KaTeX, KPIs e callouts).
- Bloqueio otimista baseado em controle estrito de versão (`version`), impedindo sobrescritas acidentais (HTTP 409 Conflict).
- Gestão de Snapshots imutáveis com histórico de versões e restauração instantânea.
- Dashboards com grade modular de tiles e filtros multi-dimensionais.
- Colaboração em tempo real via WebSockets (`/ws/reports/{report_id}`).
- Isolamento multi-tenant transparente via cabeçalho `X-Tenant-ID`.

## Portas
- Interna: `8005`
- Externa (Compose): `8015`
