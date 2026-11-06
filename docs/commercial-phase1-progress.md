# Fase Comercial 1 — Monorepo, Contratos, Armazenamento e Multi-Tenancy ✅ CONCLUÍDA (2026-11-06)

Primeira fase da transformação do protótipo monolítico no produto comercial **Metastatistic Commercial** (Enterprise B2B SaaS). Estabelece a infraestrutura de monorepo, contratos tipados unificados, desacoplamento de storage e particionamento de dados multi-inquilino (*multi-tenant*).

---

## 1. O Que Foi Construído e Entregue

### 1.1 Estrutura de Monorepo (`pnpm-workspace.yaml`)
A raiz do projeto foi reestruturada para suportar múltiplos pacotes e microsserviços integrados:
- `apps/*`: Aplicações cliente e APIs centrais (`apps/web`, `apps/api`).
- `packages/*`: Pacotes compartilhados de contratos, bibliotecas e componentes (`packages/contracts`).
- `services/*`: Microsserviços especializados de backend (`services/auth-tenant-service`, `services/gateway`, `services/stat-orchestrator`).
- `engines/*`: Runtimes analíticos isolados (`engines/r-worker`).

### 1.2 Pacote de Contratos Compartilhados (`packages/contracts`)
Implementado em TypeScript estrito, servindo como fonte única da verdade para contratos de dados compartilhados entre frontend e serviços:
- **Tenancy & IAM (`src/tenant.ts`, `src/auth.ts`)**:
  - `SubscriptionTier`: `'community' | 'team' | 'enterprise'`.
  - `Tenant`: identificador, nome, slug único, tier de assinatura e configurações.
  - `Workspace`: suporte a múltiplos ambientes de trabalho por organização.
  - `UserRole`: `'owner' | 'admin' | 'statistician' | 'analyst' | 'viewer'`.
  - `User`: metadados e papel associado ao tenant.
- **Análises & Formatação APA (`src/analysis.ts`)**:
  - `AnalysisEngine`: `'r' | 'py'`.
  - `TableAPA`: estrutura padronizada para tabelas científicas da 7ª edição da APA (`title`, `headers`, `rows`, `footnotes`, `note`).
  - `AnalysisSpec`: especificação de execução contendo tipo, motor, dataset, variáveis e opções.
  - `AnalysisResult`: status do ciclo de vida (`pending`, `running`, `completed`, `failed`), tabelas APA, figuras e diagnósticos.
- **Consultas & Storage (`src/query.ts`, `src/storage.ts`)**:
  - `QuerySpec`: consultas SQL governadas com paginação e timeout.
  - `StorageMetadata`: rastreamento de artefatos com `tenantId`, `path`, `sizeBytes`, `mimeType` e `storageBackend`.

### 1.3 Abstração de Armazenamento de Objetos (`apps/api/app/storage/`)
Camada de persistência de arquivos agnóstica a provedor implementada sob a interface abstrata `StorageProvider` (`base.py`):
- **`LocalStorageProvider` (`local.py`)**:
  - Organização determinística em diretórios por inquilino: `tenants/{tenant_id}/datasets/{id}.parquet`.
  - Suporte a tenant padrão (`default`) para retrocompatibilidade total com datasets preexistentes em `datasets/{id}.parquet`.
- **`S3StorageProvider` (`s3.py`)**:
  - Conexão com buckets compatíveis com Amazon S3 ou MinIO local via `boto3`.
  - Prefixo estruturado: `tenants/{tenant_id}/datasets/{id}.parquet`.
  - **Cache local inteligente**: downloads sob demanda com cache local indexado no diretório de dados para leitura ultrarrápida pelo DuckDB e pelos workers analíticos sem overhead contínuo de rede.
  - Fallback automático e geração de caminhos locais transitórios.
- **Fábrica e Gerenciamento (`__init__.py`)**:
  - `get_storage_provider()` e `reset_storage_provider()` com seleção automática via variável `STORAGE_BACKEND` (`local` ou `s3`).

### 1.4 Multi-Tenancy no Banco de Dados Relacional (`apps/api/app/db.py`)
- **Tabela `tenants`**:
  - Armazena organizações com `id`, `name`, `slug` único, `tier` e data de criação.
  - Auto-seed transparente da organização padrão (`id = 'default'`, `name = 'Default Organization'`, `tier = 'enterprise'`).
- **Migração Automática Não-Destrutiva**:
  - Inspeção dinâmica de schema via `PRAGMA table_info`.
  - Inclusão idempotente da coluna `tenant_id TEXT NOT NULL DEFAULT 'default'` nas tabelas principais:
    - `datasets`
    - `reports`
    - `dashboards`
    - `users`
    - `collections`
  - Garantia de que bases existentes continuam funcionando perfeitamente sem necessidade de migrações manuais ou perda de dados.

---

## 2. Decisões Tomadas e Armadilhas Contornadas

1. **Retrocompatibilidade com Datasets Legados**:
   - *Desafio*: Datasets criados nas fases anteriores estavam salvos diretamente em `<DATA_DIR>/datasets/<id>.parquet`, sem partição de inquilino.
   - *Solução*: O `LocalStorageProvider` e o `S3StorageProvider` verificam a existência do caminho particionado `tenants/{tenant_id}/datasets/{id}.parquet`; caso o tenant seja `default` e o arquivo resida no caminho legado raiz, ele é lido sem erro, assegurando compatibilidade retroativa absoluta.
2. **Descompasso Posicional em Consultas SQL (SQLite `ALTER TABLE`)**:
   - *Desafio*: Adicionar colunas `tenant_id` em tabelas existentes no SQLite altera a ordem posicional dos campos se o código fizer `INSERT INTO tabela VALUES (...)` sem elencar as colunas explicitamente.
   - *Solução*: Todos os comandos de inserção do schema inicial e testes foram revisados para citar as colunas alvo explicitamente (ex.: `INSERT INTO tenants (id, name, slug, tier, created_at) VALUES (?, ?, ?, ?, ?)`).
3. **Leitura Parquet Direta via DuckDB**:
   - *Desafio*: DuckDB precisa de caminho no sistema de arquivos local para ler arquivos Parquet eficientemente.
   - *Solução*: A abstração de storage fornece o método `get_local_path(tenant_id, filename)`, que no provedor S3 baixa e mantém o arquivo em cache local antes de repassar o caminho para o DuckDB.

---

## 3. Verificação e Testes

Todos os testes foram executados e validados com 100% de aprovação:

| Suíte de Testes | Quantidade | Status | Detalhes |
|---|---|---|---|
| `apps/api` (pytest) | **330 testes** (+66 skipped de integração R) | ✅ PASSOU | Cobre `test_storage.py` (Local/S3/Cache), `test_multitenant_db.py` (auto-seed e migrações), ACLs, RLS, transforms, relatórios e dashboards. |
| `apps/web` (vitest) | **259 testes** | ✅ PASSOU | Cobre formatação APA, gerador de blocos, transforms, filtros e dashboards. |
| Frontend Typecheck | `tsc --noEmit` | ✅ LIMPO | Zero erros de tipagem TypeScript. |
| Frontend Build | `vite build` | ✅ LIMPO | Bundle de produção gerado com sucesso em 599ms. |

---

## 4. Limitações Conhecidas

- `meta.db` central da API de dados ainda utiliza SQLite particionado por coluna `tenant_id`. A transição para PostgreSQL com Row-Level Security (RLS) completo faz parte das etapas enterprise avançadas.
- O cache do `S3StorageProvider` é mantido localmente no disco efêmero do pod/instância; em nós múltiplos de API sem volume compartilhado, cada nó baixa a sua própria cópia do Parquet quando requisitado.
