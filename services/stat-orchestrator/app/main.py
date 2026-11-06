"""Aplicação FastAPI para o microsserviço de Orquestração Estatística Dual-Engine."""
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.cache import ResultCache, deterministic_cache_key
from app.config import settings
from app.engines.python_engine import PythonStatisticalEngine
from app.engines.r_engine import REngineError, RStatisticalEngine
from app.engines.router import EngineRouter
from app.queue_manager import QueueManager

# Instâncias dos componentes centrais
python_engine = PythonStatisticalEngine()
r_engine = RStatisticalEngine()
router = EngineRouter(python_engine=python_engine, r_engine=r_engine)
cache = ResultCache(
    max_entries=settings.cache_max_entries,
    max_bytes=settings.cache_size_mb * 1024 * 1024,
)
queue_mgr = QueueManager(
    max_concurrency=settings.max_concurrent_jobs,
    router=router,
    cache=cache,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_mgr.ensure_workers()
    yield
    await queue_mgr.shutdown()


app = FastAPI(
    title="MetaStatistic Stat Orchestrator",
    version="1.0.0",
    description="Statistical Orchestration Microservice with Dual-Engine (R and Pure Python/SciPy)",
    lifespan=lifespan,
)


# Schemas Pydantic
class AnalysisPayload(BaseModel):
    analysis: str
    dataset_id: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    measurement: dict[str, str] = Field(default_factory=dict)
    engine: str | None = None
    priority: str | None = None
    data: Any = None
    timeout_s: float | None = None


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    priority: str
    engine: str


@app.get("/health")
async def health_check():
    """Retorna a saúde dos workers R, estado do engine Python e fila."""
    r_health = await r_engine.health()
    py_health = await python_engine.health()
    q_status = queue_mgr.status()

    is_healthy = py_health.get("status") == "healthy"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "stat-orchestrator",
        "engines": {
            "python": py_health,
            "r": r_health,
        },
        "queue": q_status,
    }


@app.get("/analyses/status")
async def analyses_status():
    """Métricas operacionais do pool de execução, cache e fila."""
    r_health = await r_engine.health()
    return {
        "pool": {
            "workers_total": r_health.get("workers_total", 0),
            "workers_healthy": r_health.get("workers_healthy", 0),
            "workers": r_health.get("workers", {}),
        },
        "cache": cache.stats(),
        "queue": queue_mgr.status(),
        "default_engine": settings.default_engine,
    }


@app.post("/jobs/submit", response_model=JobSubmitResponse)
async def submit_job(
    req: AnalysisPayload,
    x_tenant_id: str | None = Header(default="default", alias="X-Tenant-ID"),
    x_priority: str | None = Header(default=None, alias="X-Priority"),
):
    """Enfileira análise de forma assíncrona respeitando prioridade VIP/Enterprise vs Standard."""
    tenant_id = x_tenant_id or "default"
    priority = (x_priority or req.priority or "standard").lower()
    engine = req.engine or settings.default_engine

    job = await queue_mgr.submit_job(
        payload=req.model_dump(),
        tenant_id=tenant_id,
        priority=priority,
        engine=engine,
    )

    return JobSubmitResponse(
        job_id=job.job_id,
        status=job.status.value,
        priority=job.priority,
        engine=job.engine_requested,
    )


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Retorna situação do job, progresso e resultado quando concluído."""
    job = queue_mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' não encontrado.")
    return job.to_dict()


@app.post("/analyses/run")
async def run_analysis(
    req: AnalysisPayload,
    response: Response,
    x_tenant_id: str | None = Header(default="default", alias="X-Tenant-ID"),
    x_priority: str | None = Header(default=None, alias="X-Priority"),
):
    """Endpoint síncrono compatível com a API existente.

    Verifica cache antes de executar; se miss, submete e aguarda o job.
    """
    tenant_id = x_tenant_id or "default"
    priority = (x_priority or req.priority or "standard").lower()
    engine = req.engine or settings.default_engine

    # Chave determinística de cache
    cache_key = deterministic_cache_key(
        tenant_id=tenant_id,
        analysis=req.analysis,
        dataset_id=req.dataset_id,
        options=req.options,
        columns=req.columns,
    )

    # 1. Consulta ao cache
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_result

    response.headers["X-Cache"] = "MISS"

    # 2. Enfileiramento e aguardo síncrono
    job = await queue_mgr.submit_job(
        payload=req.model_dump(),
        tenant_id=tenant_id,
        priority=priority,
        engine=engine,
    )

    timeout = req.timeout_s or settings.analysis_timeout_s
    try:
        completed_job = await queue_mgr.wait_for_job(job.job_id, timeout_s=timeout)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    if completed_job.status.value == "failed":
        err_msg = completed_job.error or "Erro durante o processamento estatístico."
        if "não é suportada" in err_msg or "obrigatória" in err_msg or "deve conter" in err_msg:
            raise HTTPException(status_code=422, detail=err_msg)
        if "não encontrado" in err_msg:
            raise HTTPException(status_code=404, detail=err_msg)
        raise HTTPException(status_code=502, detail=err_msg)

    return completed_job.result
