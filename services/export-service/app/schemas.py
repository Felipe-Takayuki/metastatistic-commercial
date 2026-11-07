from typing import Any, Literal
from pydantic import BaseModel, Field

ExportFormat = Literal["html", "pdf", "latex", "docx", "markdown"]


class ExportRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    format: ExportFormat = "html"
    options: dict[str, Any] = Field(default_factory=dict)


class ExportResponse(BaseModel):
    filename: str
    mime_type: str
    format: ExportFormat
    content: str | None = None
    size_bytes: int = 0
