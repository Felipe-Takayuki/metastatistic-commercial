from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    name: str
    type: str
    measurementLevel: Optional[Literal["nominal", "ordinal", "scale"]] = None
    nullable: bool = True


class QueryRequest(BaseModel):
    sql: str
    dataset_id: Optional[str] = None
    limit: Optional[int] = None
    timeout_s: Optional[float] = None
    mask_pii: bool = False


class QueryResult(BaseModel):
    columns: list[ColumnMeta]
    rows: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float


class PIIMaskRule(BaseModel):
    column: str
    rule: Literal["mask_email", "mask_cpf", "mask_phone", "hash_sha256", "redact", "noise_numeric"]


class ConnectionConfig(BaseModel):
    id: str
    tenant_id: str = "default"
    name: str
    type: Literal["sqlite", "duckdb", "postgres", "mysql"]
    database: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    path: Optional[str] = None


class ConnectionTestRequest(BaseModel):
    connection: ConnectionConfig


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


class PrepStep(BaseModel):
    op: str
    params: dict[str, Any] = Field(default_factory=dict)


class TransformPreviewRequest(BaseModel):
    dataset_id: str
    steps: list[PrepStep] = Field(default_factory=list)
    limit: int = 50
    mask_pii: bool = False


class TransformPreviewResponse(BaseModel):
    columns: list[ColumnMeta]
    rows: list[dict[str, Any]]
    row_count: int
