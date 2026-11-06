from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from .. import audit, auth, datasets, permissions
from ..analysis_service import AnalysisService, cache_key, get_service
from ..pool import PoolError
from ..schemas import AnalysisRequest, AnalysisResponse
from ..security import current_user, require_viewer

router = APIRouter(prefix="/analyses", tags=["analyses"], dependencies=[Depends(require_viewer)])


def _strings(value: Any):
    """Todas as strings dentro de uma estrutura de opções (listas/dicts aninhados)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def referenced_columns(ds: datasets.Dataset, options: dict[str, Any]) -> list[str]:
    """Colunas citadas nas opções; o worker só lê essas do Parquet. Se nenhuma bater, lê todas."""
    mentioned = set(_strings(options))
    cols = [c.name for c in ds.columns if c.name in mentioned]
    return cols or [c.name for c in ds.columns]


@router.get("/status")
async def analyses_status(service: AnalysisService = Depends(get_service)) -> dict[str, Any]:
    """Situação do motor: workers (total/ocupados/fora), fila, cache. A interface mostra isso quando uma análise demora."""
    return service.status()


@router.post("/run", response_model=AnalysisResponse)
async def run_analysis(req: AnalysisRequest, service: AnalysisService = Depends(get_service), user: auth.User = Depends(current_user)) -> AnalysisResponse:
    try:
        ds = datasets.get_dataset(req.dataset_id)
    except datasets.DatasetNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    if not permissions.can_read(user, ds.id):
        audit.log(user, "denied", "dataset", ds.id, "analysis")
        raise HTTPException(404, f"dataset not found: {req.dataset_id}")
    source = await run_in_threadpool(permissions.analysis_source, user, ds)  # cópia filtrada por linha, se houver regra
    columns = referenced_columns(ds, req.options)
    measurement = {c.name: c.measurement for c in ds.columns if c.name in columns}
    payload = {
        "analysis": req.analysis,
        "dataset_id": source,
        "options": req.options,
        "columns": columns,
        "measurement": measurement,
    }
    key = cache_key(req.analysis, source, req.options, columns, measurement)
    try:
        body = await service.run(key, payload)
    except PoolError as exc:  # fila cheia/espera longa (429/503), motor fora (503), timeout (504), erro da análise (422/502)
        raise HTTPException(exc.status_code, exc.message) from exc
    except Exception as exc:  # falha inesperada falando com o worker (conexão cortada no meio, etc.)
        raise HTTPException(502, f"Erro ao falar com o motor estatístico: {type(exc).__name__}") from exc
    return AnalysisResponse(**body)
