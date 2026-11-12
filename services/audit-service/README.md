# MetaStatistic Commercial — Audit Service

Microsserviço de **trilha de auditoria imutável** (SOC 2 Type II / FDA 21 CFR Part 11). Extraído do `auth-tenant-service`:
agora tem processo, banco SQLite (`audit.db`) e volume próprios.

## Funcionalidades
- **Cadeia de hash SHA-256 por tenant**: cada evento guarda `prev_hash` e `record_hash`; adulterar ou remover um registro rompe a cadeia.
- **Verificação de integridade**: `GET /audit/verify` recalcula a cadeia e aponta o primeiro registro adulterado. Com `tenant_id` verifica a cadeia dele; sem, verifica a cadeia de cada tenant separadamente.
- **Exportação com atestado**: `GET /audit/export` devolve os eventos em ordem cronológica + `integrity_verified`.

## Endpoints
- `GET /health`
- `POST /audit/events` — registra um evento (usado pelo `auth-tenant-service` e por qualquer outro serviço)
- `GET /audit/events?tenant_id=&user_id=&action=&limit=&offset=`
- `GET /audit/verify?tenant_id=`
- `GET /audit/export?tenant_id=`

O gateway roteia `/api/v1/audit/*` e `/audit/*` para este serviço (`AUDIT_SERVICE_URL`).

## Configuração
| Variável | Padrão |
|---|---|
| `PORT` | `8008` |
| `DATABASE_URL` | `sqlite:///./audit.db` |

## Migrando eventos do auth-tenant-service
Antes da extração os eventos ficavam na tabela `audit_log` do `auth_tenant.db`. Para trazê-los (com hashes preservados) **antes de o
serviço receber tráfego**:
```bash
python -m audit_service.import_legacy /caminho/para/auth_tenant.db
```
É idempotente e não altera o banco de origem.

## Execução Local
```bash
uv run uvicorn audit_service.main:app --port 8008 --reload
```

## Testes
```bash
uv run pytest
```
