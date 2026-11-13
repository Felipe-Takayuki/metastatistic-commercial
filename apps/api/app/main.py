from fastapi import FastAPI

from .routers import analyses, collections, dashboards, datasets, queries, reports, transforms
from .routers import auth as auth_router
from .tenancy import TenantMiddleware

app = FastAPI(title="Metastatistic API", version="0.1.0")
app.add_middleware(TenantMiddleware)  # organização verificada pelo gateway (X-Tenant-ID); ver tenancy.py
app.include_router(auth_router.router)
app.include_router(auth_router.users_router)
app.include_router(auth_router.audit_router)
app.include_router(collections.router)
app.include_router(datasets.router)
app.include_router(queries.router)
app.include_router(analyses.router)
app.include_router(transforms.router)
app.include_router(reports.router)
app.include_router(dashboards.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
