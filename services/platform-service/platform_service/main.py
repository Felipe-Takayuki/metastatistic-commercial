"""Platform: audit, auth-tenant, billing, bi-report e export no MESMO processo.

Cada um desses serviços custa ~50 MB de memória só pelo interpretador + FastAPI + pydantic; juntos em um processo
o custo base é pago uma vez (útil em VPS pequeno). Cada serviço continua sendo o mesmo app FastAPI de antes (os
Dockerfiles individuais seguem funcionando); aqui eles apenas são montados sob prefixos:

    /_audit  /_auth  /_billing  /_bi  /_export

O gateway aponta para esses prefixos (ex.: AUTH_SERVICE_URL=http://platform:8000/_auth) e os caminhos que cada serviço
enxerga são os de sempre (o Starlette remove o prefixo). Como os serviços leem a mesma variável DATABASE_URL, no modo
platform use AUDIT_/AUTH_/BILLING_/BI_DATABASE_URL.
"""
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from audit_service.main import app as audit_app
from auth_tenant_service.main import app as auth_app
from bi_report_service.main import app as bi_app
from billing_service.main import app as billing_app
from export_service.main import app as export_app

MOUNTS: dict[str, FastAPI] = {
    "/_audit": audit_app,
    "/_auth": auth_app,
    "/_billing": billing_app,
    "/_bi": bi_app,
    "/_export": export_app,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # O Starlette NÃO executa o lifespan de apps montados (auth e bi inicializam seus bancos nele).
    async with AsyncExitStack() as stack:
        for sub in MOUNTS.values():
            await stack.enter_async_context(sub.router.lifespan_context(sub))
        yield


app = FastAPI(title="Metastatistic Platform", version="1.0.0", lifespan=lifespan)
for _prefix, _sub in MOUNTS.items():
    app.mount(_prefix, _sub)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "platform", "mounts": sorted(MOUNTS)}
