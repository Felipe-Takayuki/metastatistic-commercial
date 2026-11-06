from fastapi import APIRouter, Depends, HTTPException

from .. import auth, queries
from ..schemas import QueryRequest, QueryResult

from ..security import current_user, require_viewer

router = APIRouter(prefix="/queries", tags=["queries"], dependencies=[Depends(require_viewer)])


@router.post("/run", response_model=QueryResult)
def run_query(req: QueryRequest, user: auth.User = Depends(current_user)) -> QueryResult:
    """Executa SQL somente leitura sobre os datasets (tabela = `table_name` do dataset)."""
    try:
        return queries.run_query(req.sql, req.limit, user=user)
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc
