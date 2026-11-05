"""Contratos da API. Independentes do formato interno do jaspResults / do DuckDB."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Measurement = Literal["nominal", "ordinal", "scale"]


class Column(BaseModel):
    name: str
    dtype: str = Field(description="Tipo SQL (DuckDB), ex.: BIGINT, VARCHAR, DATE")
    measurement: Measurement = Field(description="Nível de medida, como no JASP")
    n_distinct: int | None = None


class Dataset(BaseModel):
    id: str
    name: str
    table_name: str = Field(description="Nome usado em SQL: SELECT * FROM <table_name>")
    n_rows: int
    columns: list[Column]
    created_at: str


class DatasetFromQuery(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sql: str = Field(min_length=1, max_length=100_000)


class DatasetPatch(BaseModel):
    measurement: dict[str, Measurement] = Field(description="coluna -> novo nível de medida")


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=100_000)
    limit: int | None = Field(default=None, ge=1, description="Menor ou igual ao limite do servidor")


class QueryColumn(BaseModel):
    name: str
    dtype: str


class QueryResult(BaseModel):
    columns: list[QueryColumn]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int


class AnalysisRequest(BaseModel):
    analysis: str = Field(description="Nome da análise JASP, ex.: TTestIndependentSamples")
    dataset_id: str
    options: dict[str, Any] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    status: str
    results: dict[str, Any]


# --- Relatórios -------------------------------------------------------------
from typing import Annotated, Union  # noqa: E402

from pydantic import StringConstraints, field_validator  # noqa: E402

BlockId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
MAX_BLOCKS = 100


class ChartConfig(BaseModel):
    type: Literal["bar", "line", "scatter"]
    x: str = Field(max_length=200)
    ys: list[str] = Field(max_length=3)
    slots: dict[str, int] = Field(default_factory=dict, description="coluna -> posição fixa na paleta (0..2)")


class TextBlock(BaseModel):
    type: Literal["text"]
    id: BlockId
    markdown: str = Field(default="", max_length=50_000)


class ChartBlock(BaseModel):
    type: Literal["chart"]
    id: BlockId
    title: str = Field(default="", max_length=200)
    sql: str = Field(default="", max_length=100_000)
    chart: ChartConfig | None = None


class AnalysisBlock(BaseModel):
    type: Literal["analysis"]
    id: BlockId
    analysis: str = Field(max_length=100)
    dataset_id: str = Field(max_length=64)
    options: dict[str, Any] = Field(default_factory=dict)


Block = Annotated[Union[TextBlock, ChartBlock, AnalysisBlock], Field(discriminator="type")]


class ReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    blocks: list[Block] = Field(default_factory=list, max_length=MAX_BLOCKS)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v

    @field_validator("blocks")
    @classmethod
    def _unique_ids(cls, blocks: list) -> list:
        ids = [b.id for b in blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("block ids must be unique within a report")
        return blocks


class ReportUpdate(ReportIn):
    version: int = Field(ge=1, description="versão que o cliente está editando (bloqueio otimista)")


class Report(ReportIn):
    id: str
    version: int
    created_at: str
    updated_at: str
