# Fase Comercial 3 — Microsserviço de Consulta, Conectores e Data Prep (`data-engine-service`) ✅ CONCLUÍDA (2026-11-07)

Terceira fase da transição para microsserviços do **Metastatistic Commercial**. Entrega o serviço dedicado de computação analítica rápida, isolamento de consultas com DuckDB, streaming de tabelas com Apache Arrow IPC, mascaramento de dados sensíveis (PII Masking) e abstração de conectores externos (`data-engine-service`), além da integração no API Gateway e no Docker Compose.

---

## 1. O Que Foi Construído e Entregue

### 1.1 Microsserviço de Consulta Analítica (`services/data-engine-service`)
Operando de forma independente na porta `8004` (mapeada para `8014` no host):

- **DuckDB Sandbox com Validação em Camadas**:
  - Validação de SQL via `sqlglot` antes de tocar no banco de dados.
  - Garante exatamente 1 instrução SQL e restringe a execução exclusivamente a consultas de leitura (`SELECT` / `exp.Query`).
  - Bloqueio estrito de operações DDL/DML (`DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`, `COMMAND`).
  - Bloqueio de chamadas maliciosas a funções de tabela (`read_csv`, `read_parquet`, `range`, `system`).
  - Sandbox DuckDB em memória com isolamento de diretórios do inquilino (`tenants/{tenant_id}/datasets` ou `datasets`), com flags:
    - `memory_limit` configurável (padrão 512MB).
    - `threads` limitadas (padrão 2).
    - `enable_external_access=false` e `lock_configuration=true`.
    - Interrupt preemptivo com `threading.Timer` para timeout seguro de consultas.

- **Streaming Binário com Apache Arrow IPC**:
  - Endpoint `POST /queries/arrow` que serializa a tabela analítica do DuckDB diretamente no formato padrão da indústria `application/vnd.apache.arrow.stream` via `pyarrow.ipc.RecordBatchStreamWriter`.
  - Zero-copy na geração e deserialização, permitindo que clientes (incluindo o stat-orchestrator e frontends modernos) recebam conjuntos massivos de dados analíticos com mínima sobrecarga de serialização JSON.

- **Motor de Anonimização e Mascaramento de PII**:
  - `mask_email(val)`: preserva primeiro e último caractere do usuário antes do `@` (ex.: `j***e@domain.com`).
  - `mask_cpf(val)`: sanitiza dígitos e mascara os blocos identificadores e verificadores (ex.: `***.456.789-**`).
  - `mask_phone(val)`: preserva DDD e 4 últimos dígitos, mascarando os centrais (ex.: `(11) 9****-1234`).
  - `hash_sha256(val, salt)`: hash determinístico truncado em 16 caracteres hexadecimais, utilizando o `tenant_id` como salt criptográfico para evitar rainbow tables cruzadas entre clientes.
  - `redact(val)`: substitui integralmente pelo marcador `[REDACTED]`.
  - `noise_numeric(val, pct)`: adição determinística de ruído proporcional para atributos numéricos sensíveis.
  - `auto_detect_and_mask_pii(rows, tenant_id)`: varre dinamicamente os nomes das colunas e aplica automaticamente a regra de conformidade correspondente (LGPD / GDPR).

- **Data Prep & Transform Preview Engine (`POST /transforms/preview`)**:
  - Permite aos analistas pré-visualizarem transformações estruturadas antes de persistir alterações:
    - `select`: projeção de colunas desejadas.
    - `rename`: renomeação de atributos com cláusula `RENAME`.
    - `filter`: aplicação de predicados booleanos e filtros condicionais.
    - `sort`: ordenação ascendente ou descendente.
    - `cast`: coerção explícita de tipos de dados.
  - Suporte ao flag `mask_pii=True` para anonimizar os dados no preview.

- **Gerenciador de Conectores Externos (`ConnectionManager`)**:
  - Endpoints `POST /connections`, `GET /connections` e `POST /connections/test`.
  - Teste e validação de conexões para:
    - `sqlite`: validação em memória ou caminho local.
    - `duckdb`: validação de integridade do arquivo ou instância.
    - `postgres` e `mysql`: handshake de rede e conectividade com timeout estrito de 2s e medição de latência (`latency_ms`).

### 1.2 Atualização do API Gateway (`services/gateway`)
- **Roteamento Dinâmico Atualizado**:
  - `/api/v1/queries/*` e `/queries/*` ➔ `http://data-engine-service:8004`
  - `/api/v1/transforms/*` e `/transforms/*` ➔ `http://data-engine-service:8004`
  - `/api/v1/connections/*` e `/connections/*` ➔ `http://data-engine-service:8004`
- **Health Check Agregador Consolidado**:
  - `GET /health` agora inspeciona os quatro serviços downstream: `auth_tenant_service`, `stat_orchestrator`, `data_engine` e `data_api`.

### 1.3 Orquestração Docker Compose (`docker-compose.microservices.yml`)
- Adição do serviço `data-engine-service`:
  - Imagem `metastatistic-data-engine-service:latest`.
  - Portas: `8014:8004`.
  - Volume de datasets montado como somente leitura (`datasets:/data:ro`).
  - Variável de ambiente `DATA_ENGINE_SERVICE_URL` injetada no `gateway`.
  - Dependência explícita adicionada na diretiva `depends_on` do `gateway`.

---

## 2. Decisões Técnicas e Medidas de Segurança

1. **Defesa em Profundidade para Consultas Analíticas**:
   - As consultas SQL são primeiro analisadas sintaticamente via AST (`sqlglot`). Qualquer tentativa de DDL, injeção de múltiplos statements ou chamadas a funções de tabela como `read_parquet(...)` ou `system(...)` é abortada antes mesmo de tocar no motor de banco.
   - O DuckDB roda com `enable_external_access=false` e `lock_configuration=true`, impossibilitando que mesmo consultas complexas acessem arquivos fora dos Parquets expressamente autorizados.
2. **Zero-Copy com DuckDB Relation para Arrow IPC**:
   - Em vez de serializar pelo cursor genérico DB-API (que gerava avisos de cópia extra de memória), o motor utiliza diretamente `con.sql(query).to_arrow_table()`, mantendo o alinhamento de memória nativo em Apache Arrow e transmitindo os bytes em alta velocidade.
3. **Isolamento de Salting em Hashing PII**:
   - O hashing criptográfico SHA-256 para anonimização utiliza o `tenant_id` como salt obrigatório, garantindo que o mesmo identificador em dois inquilinos diferentes gere hashes completamente distintos, impedindo ataques de correlação multi-inquilino.

---

## 3. Cobertura e Resultados dos Testes

Todos os testes automatizados da plataforma foram executados e aprovados:

| Serviço | Testes Aprovados | Tempo de Execução | Status |
| :--- | :---: | :---: | :---: |
| `services/data-engine-service` | 10 / 10 | 0.75s | ✅ Aprovado |
| `services/gateway` | 8 / 8 | 0.45s | ✅ Aprovado |
| `services/auth-tenant-service` | 6 / 6 | 0.50s | ✅ Aprovado |
| `services/stat-orchestrator` | 13 / 13 | 1.84s | ✅ Aprovado |
| `apps/api` | 330 / 330 (66 skipped) | 51.77s | ✅ Aprovado |

**Total de testes de microsserviços e API:** 367 testes passando com 100% de sucesso.
