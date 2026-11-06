from fastapi import FastAPI

from .routers import analyses, dashboards, datasets, queries, reports
from .routers import auth as auth_router

app = FastAPI(title="Metastatistic API", version="0.1.0")
app.include_router(auth_router.router)
app.include_router(auth_router.users_router)
app.include_router(datasets.router)
app.include_router(queries.router)
app.include_router(analyses.router)
app.include_router(reports.router)
app.include_router(dashboards.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
