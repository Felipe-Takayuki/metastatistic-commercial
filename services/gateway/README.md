# MetaStatistic API Gateway

API Gateway e Proxy Reverso assíncrono para os microsserviços do MetaStatistic.

## Recursos

- **Tenant Resolution**: Identifica o tenant por:
  1. Header `X-Tenant-ID` ou `X-Tenant-Slug`
  2. Subdomínio da requisição (`acme.metastatistic.com` -> `acme`)
  3. Claim `tenant_id` no JWT Bearer token
  4. Fallback para `DEFAULT_TENANT_ID`
- **Roteamento Inteligente**:
  - `/api/v1/auth/*` e `/api/v1/tenants/*` -> `AUTH_SERVICE_URL`
  - `/api/v1/*` (datasets, queries, analyses, reports, etc.) -> `DATA_API_URL`
- **Propagação de Cabeçalhos**: Injeta `X-Tenant-ID`, `X-Tenant-Slug`, `X-Forwarded-For`, etc.
- **Health Aggregation**: `/health` verifica os serviços downstream e relata status detalhado.

## Portas Padrão

- Gateway: `8080`
- Auth Service downstream: `8002`
- Data API downstream: `8000`
