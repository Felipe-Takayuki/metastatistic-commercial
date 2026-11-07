import io
from typing import List, Optional
import duckdb
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pyarrow as pa

from app.config import settings
from app.connectors import manager as conn_manager
from app.prep_engine import preview_transforms
from app.query_engine import (
    QueryEngineError,
    execute_query,
    execute_query_arrow_stream,
)
from app.schemas import (
    ConnectionConfig,
    ConnectionTestRequest,
    ConnectionTestResponse,
    QueryRequest,
    QueryResult,
    TransformPreviewRequest,
    TransformPreviewResponse,
)

app = FastAPI(
    title="MetaStatistic Data Engine Service",
    version="0.1.0",
    description="Microservice for analytical querying (DuckDB sandbox), Arrow IPC streaming, PII masking, and data connectors.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "data-engine-service",
        "duckdb_version": duckdb.__version__,
        "arrow_version": pa.__version__,
    }


@app.post("/queries/run", response_model=QueryResult)
def run_query_endpoint(
    req: QueryRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = x_tenant_id or "default"
    try:
        return execute_query(
            sql=req.sql,
            tenant_id=tenant_id,
            dataset_id=req.dataset_id,
            limit=req.limit,
            timeout_s=req.timeout_s,
            mask_pii=req.mask_pii,
        )
    except QueryEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected query error: {str(exc)}")


@app.post("/queries/arrow")
def run_query_arrow_endpoint(
    req: QueryRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = x_tenant_id or "default"
    try:
        arrow_bytes = execute_query_arrow_stream(
            sql=req.sql,
            tenant_id=tenant_id,
            dataset_id=req.dataset_id,
            limit=req.limit,
            timeout_s=req.timeout_s,
        )
        return StreamingResponse(
            io.BytesIO(arrow_bytes),
            media_type="application/vnd.apache.arrow.stream",
            headers={
                "Content-Disposition": 'attachment; filename="query_result.arrow"',
                "X-Tenant-ID": tenant_id,
            },
        )
    except QueryEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected query error: {str(exc)}")


@app.post("/transforms/preview", response_model=TransformPreviewResponse)
def transform_preview_endpoint(
    req: TransformPreviewRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = x_tenant_id or "default"
    try:
        return preview_transforms(
            dataset_id=req.dataset_id,
            steps=req.steps,
            limit=req.limit,
            tenant_id=tenant_id,
            mask_pii=req.mask_pii,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Transform error: {str(exc)}")


@app.post("/connections/test", response_model=ConnectionTestResponse)
def test_connection_endpoint(req: ConnectionTestRequest):
    return conn_manager.test_connection(req.connection)


@app.post("/connections", response_model=ConnectionConfig)
def create_connection_endpoint(
    config: ConnectionConfig,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = x_tenant_id or config.tenant_id or "default"
    config.tenant_id = tenant_id
    return conn_manager.register_connection(config)


@app.get("/connections", response_model=List[ConnectionConfig])
def list_connections_endpoint(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    tenant_id = x_tenant_id or "default"
    return conn_manager.list_connections(tenant_id)
