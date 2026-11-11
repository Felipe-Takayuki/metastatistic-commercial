# Auth & Tenant Service

Microsserviço responsável pela gestão de Identidade, Organizações (Tenants), Associações de Usuários (RBAC), Convites e Quotas por Tier (`community`, `team`, `enterprise`).

## Recursos

- **Multi-Tenancy**: Criação e consulta de organizações via ID e Slug.
- **RBAC**: Papéis `owner`, `admin`, `statistician`, `analyst`, `viewer`.
- **Proteção do Proprietário**: Impede exclusão ou rebaixamento do único proprietário do tenant.
- **Quotas por Tier**:
  - `community`: até 3 membros, 10 datasets, 500 MB.
  - `team`: até 15 membros, 100 datasets, 10 GB.
  - `enterprise`: membros ilimitados, sem limites rígidos de armazenamento.
- **JWT (HS256)**: Geração e validação de tokens com claims `sub`, `tenant_id`, `role`, `tier`, `exp`.

## Endpoints

- `GET /health`
- `POST /tenants`
- `GET /tenants/{tenant_id}`
- `GET /tenants/by-slug/{slug}`
- `POST /tenants/{tenant_id}/invitations`
- `POST /tenants/invitations/{token}/accept`
- `GET /tenants/{tenant_id}/members`
- `PATCH /tenants/{tenant_id}/members/{user_id}`
- `DELETE /tenants/{tenant_id}/members/{user_id}`
- `POST /auth/token`
- `POST /auth/verify`

## Auditoria
A trilha de auditoria imutável vive no [`audit-service`](../audit-service/README.md). Este serviço apenas envia os eventos
(`tenant.create`, `member.role_update`, `auth.token_issued`, `sso.*`, `scim.*`, …) para `POST {AUDIT_SERVICE_URL}/audit/events`.
O envio é best-effort: se o audit-service estiver fora do ar, o erro é logado e a operação principal segue. Defina
`AUDIT_SERVICE_URL=""` para desativar o envio.
