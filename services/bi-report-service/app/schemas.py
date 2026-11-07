from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

BlockType = Literal[
    "text",
    "heading",
    "chart",
    "table_apa",
    "equation",
    "kpi",
    "callout",
    "analysis",
]


class ReportBlock(BaseModel):
    id: str = Field(..., description="Identificador único do bloco")
    type: BlockType = Field(..., description="Tipo semântico do bloco")
    content: dict[str, Any] | str = Field(default="", description="Conteúdo textual, estruturado ou configuração")
    order: int = Field(default=0, description="Ordem de exibição do bloco")


class ReportIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    blocks: list[ReportBlock] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be empty or only whitespace")
        return s


class ReportUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    blocks: list[ReportBlock] = Field(default_factory=list)
    version: int = Field(..., ge=1, description="Versão atual esperada para bloqueio otimista")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be empty or only whitespace")
        return s


class Report(BaseModel):
    id: str
    tenant_id: str
    title: str
    blocks: list[ReportBlock]
    version: int
    created_at: str
    updated_at: str


class ReportSnapshot(BaseModel):
    id: str
    report_id: str
    tenant_id: str
    version: int
    title: str
    blocks: list[ReportBlock]
    created_at: str
    note: str = ""


class DashboardTile(BaseModel):
    id: str
    type: str = "chart"
    title: str = ""
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4
    config: dict[str, Any] = Field(default_factory=dict)


class DashboardIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    tiles: list[DashboardTile] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be empty or only whitespace")
        return s


class DashboardUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    tiles: list[DashboardTile] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    version: int = Field(..., ge=1, description="Versão atual esperada para bloqueio otimista")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be empty or only whitespace")
        return s


class Dashboard(BaseModel):
    id: str
    tenant_id: str
    title: str
    tiles: list[DashboardTile]
    filters: list[dict[str, Any]]
    version: int
    created_at: str
    updated_at: str
