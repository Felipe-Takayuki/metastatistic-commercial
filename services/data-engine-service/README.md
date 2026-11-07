# Data Engine Service

Microsserviço de consulta analítica, conectores externos, sanitização/anonimização de dados (PII Masking) e streaming de dados de alto desempenho via Apache Arrow IPC e DuckDB.

## Funcionalidades
- **DuckDB SQL Sandbox**: Execução segura e isolada de consultas SQL SELECT com validação prévia via `sqlglot`. Bloqueio de DDL/DML e chamadas arriscadas a funções de tabela.
- **Arrow IPC Binary Streaming**: Serialização zero-copy direta em stream binário (`application/vnd.apache.arrow.stream`) para transporte eficiente de tabelas analíticas.
- **PII Masking & Anonymization Engine**: Suporte a máscaras de e-mail, CPF, telefone, redaction total e hashing criptográfico SHA-256 salgado com isolamento por tenant.
- **Connectors**: Gerenciamento e teste de conexões a bancos de dados externos (SQLite, DuckDB, PostgreSQL, MySQL).
- **Data Prep Engine**: Preview ágil de transformações de dados (select, rename, filter, sort, cast).
