from fastapi import APIRouter, Depends, HTTPException

from .. import queries
from ..schemas import QueryRequest, QueryResult

from ..security import require_viewer

router = APIRouter(prefix="/queries", tags=["queries"], dependencies=[Depends(require_viewer)])


@router.post("/run", response_model=QueryResult)
def run_query(req: QueryRequest) -> QueryResult:
    """Executa SQL somente leitura sobre os datasets (tabela = `table_name` do dataset)."""
    try:
        return queries.run_query(req.sql, req.limit)
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc
