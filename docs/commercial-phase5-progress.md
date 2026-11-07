# Fase Comercial 5 — Microsserviço de Relatórios/BI, Exportação Multi-formato e Pacote Embeddable ✅ CONCLUÍDA (2026-11-07)

Quinta fase da transformação comercial do **Metastatistic Commercial**. Introduz os microsserviços `bi-report-service` e `export-service`, o pacote `@metastatistic/react-embed`, além de atualizar o API Gateway (`gateway`), o `docker-compose.microservices.yml` e toda a infraestrutura de testes automatizados e contratos.

---

## 1. O Que Foi Construído e Entregue

### 1.1 Microsserviço de BI e Relatórios Colaborativos (`services/bi-report-service`)
Localizado na porta interna `8005` (porta externa `8015` no Docker Compose), isola a gestão de relatórios executivos, dashboards analíticos, histórico de versões e colaboração em tempo real:

- **Controle Estrito de Versão e Bloqueio Otimista**:
  - Tanto `reports` quanto `dashboards` possuem controle de versão numérico monotônico (`version`).
  - Atualizações concorrentes verificam a versão esperada do cliente: caso o recurso tenha sido alterado em paralelo, a requisição é rejeitada de imediato com **HTTP 409 Conflict**, impedindo sobrescrita silenciosa de análises críticas.
- **Histórico e Snapshots Imutáveis**:
  - `POST /reports/{id}/snapshots`: captura o estado congelado do relatório com notas de auditoria (`note`).
  - `GET /reports/{id}/snapshots`: listagem cronológica reversa de versões capturadas.
  - `POST /reports/{id}/snapshots/{snapshot_id}/restore`: restauração instantânea do conteúdo de qualquer snapshot histórico, incrementando a versão do relatório e preservando a trilha de integridade.
- **Dashboards Modulares e Filtros Globais**:
  - Gestão de tiles flexíveis (`kpi`, `chart`, `text`, etc.) com coordenadas de grade (`x`, `y`, `w`, `h`) e configurações dinâmicas.
  - Suporte a filtros multi-dimensionais por tenant.
- **Colaboração em Tempo Real via WebSockets**:
  - Endpoint `/ws/reports/{report_id}` gerenciado por `WebSocketManager`.
  - Agrupamento de conexões em salas temáticas por `report_id`.
  - Broadcast de eventos de entrada/saída (`USER_JOINED`, `USER_LEFT`), atualizações de blocos (`BLOCK_UPDATED`) e movimentação de cursores.
- **Isolamento Multi-Tenant Transparente**:
  - Todas as consultas, alterações e listagens filtram estritamente pelo identificador fornecido no cabeçalho `X-Tenant-ID` (ou query parameter em WebSockets), garantindo segregação total entre inquilinos.

### 1.2 Microsserviço de Exportação Multi-formato (`services/export-service`)
Localizado na porta interna `8006` (porta externa `8016` no Docker Compose), converte blocos e estruturas analíticas em documentos formais e publicáveis em múltiplos formatos:

1. **HTML Editorial & PDF Ready (APA 7th)**:
   - Implementa regras de **CSS Paged Media**:
     - `@page { size: A4; margin: 2.5cm; @bottom-right { content: counter(page); } }`.
     - Quebras de página inteligentes (`page-break-inside: avoid` em tabelas e figuras).
   - Formatação estrita das diretrizes **APA 7th**:
     - Numeração de tabela em negrito (`Table 1`) e título em itálico abaixo.
     - Linhas horizontais estritas (borda superior, borda abaixo dos cabeçalhos e borda inferior), sem linhas verticais.
     - Notas de rodapé com prefixo itálico (`Note.`).
2. **LaTeX Acadêmico (`app/generators/latex_gen.py`)**:
   - Gera documento `\documentclass[12pt,a4paper]{article}` compilável.
   - Utiliza o pacote `booktabs` (`\toprule`, `\midrule`, `\bottomrule`) para renderização tipográfica de tabelas APA.
   - Suporte a fórmulas matemáticas com o pacote `amsmath` (`\begin{equation}`).
   - Escape de caracteres reservados do TeX para evitar falhas de compilação.
3. **Microsoft Word DOCX (`app/generators/docx_gen.py`)**:
   - Geração direta de binários DOCX via `python-docx`.
   - Formatação tipográfica profissional em Times New Roman (20pt para título, 12pt com recuo de parágrafo de 0.5 polegadas e entrelinha de 1.5 para corpo de texto).
   - Tabelas estruturadas sem bordas verticais, com cabeçalhos destacados e legendas formais.
   - Suporte a retorno binário direto (`raw=true` com `Content-Disposition: attachment`) ou payload JSON em Base64.
4. **Markdown GFM (`app/generators/markdown_gen.py`)**:
   - Padrão GitHub Flavored Markdown limpo com tabelas tabulares em texto, callouts e blocos matemáticos KaTeX (`$$...$$`).
5. **Roteador Unificado (`POST /export/generate`)**:
   - Rota polimórfica que aceita o parâmetro `format: "html" | "pdf" | "latex" | "docx" | "markdown"` e despacha para o respectivo gerador.

### 1.3 Pacote Embeddable `@metastatistic/react-embed` (`packages/react-embed`)
SDK React leve, seguro e com tipagem estrita para embutir dashboards, relatórios, gráficos e tabelas APA em portais de clientes externos:

- **Segurança Sandbox**:
  - Renderiza `iframe` com sandbox restritivo (`sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`).
  - Isolamento de scripts e proteção contra ataques de clickjacking.
- **Comunicação Bidirecional via `postMessage`**:
  - Listener para eventos emitidos pelo iframe: `FILTER_CHANGE`, `ROW_SELECT`, `HEIGHT_CHANGE`, `ERROR`.
  - Disparo de callbacks nativos do React: `onEvent`, `onError`, `onLoad`.
  - Envio de mutações dinâmicas ao iframe quando propriedades como `theme` ou `filters` são alteradas pelo container pai.
- **Auto-redimensionamento (`autoResize`)**:
  - Ajusta dinamicamente a altura do container quando o conteúdo interno do relatório emite evento `HEIGHT_CHANGE`.
- **Utilitário de Construção de URLs (`buildEmbedUrl`)**:
  - Geração segura de URLs com codificação correta de parâmetros, tema, tenant e tokens de autenticação.

### 1.4 API Gateway Atualizado (`services/gateway`)
- Novas rotas no proxy reverso:
  - `/api/v1/reports/*`, `/api/v1/dashboards/*` e `/ws/*` ➔ roteados para `BI_REPORT_SERVICE_URL`.
  - `/api/v1/export/*` ➔ roteado para `EXPORT_SERVICE_URL`.
  - Rotas diretas `/reports/*`, `/dashboards/*` e `/export/*` mapeadas com propagação do cabeçalho canônico `X-Tenant-ID`.
- Proxy WebSocket bidirecional em `/ws/{path:path}` conectando clientes externos ao `bi-report-service`.
- Healthcheck unificado (`GET /health`) estendido para monitorar a saúde de `bi_report_service` e `export_service`.

### 1.5 Docker Compose Atualizado (`docker-compose.microservices.yml`)
- Adicionados os serviços `bi-report-service` (porta `8015:8005`) e `export-service` (porta `8016:8006`).
- Adicionado volume persistente `bi_data` para SQLite do microsserviço de relatórios.
- Atualizadas dependências e variáveis de ambiente do `gateway`.

---

## 2. Resultados dos Testes Automatizados

Todos os microsserviços e pacotes foram testados e atingiram **100% de sucesso**:

| Módulo | Tipo | Testes | Status |
| :--- | :--- | :---: | :---: |
| `services/bi-report-service` | Pytest (Python 3.14/3.12) | 6 | ✅ Passou (0.24s) |
| `services/export-service` | Pytest (Python 3.14/3.12) | 6 | ✅ Passou (0.32s) |
| `services/data-engine-service` | Pytest (Python 3.14/3.12) | 10 | ✅ Passou (0.41s) |
| `services/stat-orchestrator` | Pytest (Python 3.14/3.12) | 13 | ✅ Passou (0.74s) |
| `services/auth-tenant-service` | Pytest (Python 3.14/3.12) | 6 | ✅ Passou (0.20s) |
| `services/gateway` | Pytest (Python 3.14/3.12) | 9 | ✅ Passou (0.22s) |
| `packages/react-embed` | Node Test Runner / TypeScript | 3 | ✅ Passou (53ms) |
| `apps/web` | Vitest (TypeScript) | 259 | ✅ Passou (0.64s) |
| **Total Global** | **Monorepo** | **312 testes** | **100% Sucesso** |
