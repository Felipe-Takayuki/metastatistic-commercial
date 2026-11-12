import base64
import re
from typing import Any
from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from export_service.config import settings
from export_service.generators.docx_gen import generate_docx
from export_service.generators.html_pdf_gen import generate_html
from export_service.generators.latex_gen import generate_latex
from export_service.generators.markdown_gen import generate_markdown
from export_service.schemas import ExportFormat, ExportRequest, ExportResponse

app = FastAPI(
    title="MetaStatistic Export Service",
    version="0.1.0",
    description="Multi-format document generation microservice supporting APA 7th HTML, LaTeX, DOCX and Markdown",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_filename(title: str, extension: str) -> str:
    cleaned = re.sub(r"[^\w\-_.]", "_", title.strip())[:60]
    return f"{cleaned or 'report'}.{extension}"


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "export-service",
        "version": "0.1.0",
    }


@app.post("/export/html")
def export_html(request: ExportRequest, raw: bool = Query(default=False)):
    html_content = generate_html(request.title, request.blocks, request.options)
    filename = _safe_filename(request.title, "html")
    if raw:
        return Response(
            content=html_content,
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    return ExportResponse(
        filename=filename,
        mime_type="text/html",
        format="html",
        content=html_content,
        size_bytes=len(html_content.encode("utf-8")),
    )


@app.post("/export/pdf")
def export_pdf(request: ExportRequest, raw: bool = Query(default=False)):
    """Gera HTML paged-media otimizado para motores de impressão PDF."""
    options = dict(request.options)
    options["pdf_mode"] = True
    html_paged = generate_html(request.title, request.blocks, options)
    filename = _safe_filename(request.title, "pdf.html")
    if raw:
        return Response(
            content=html_paged,
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    return ExportResponse(
        filename=filename,
        mime_type="text/html",
        format="pdf",
        content=html_paged,
        size_bytes=len(html_paged.encode("utf-8")),
    )


@app.post("/export/latex")
def export_latex(request: ExportRequest, raw: bool = Query(default=False)):
    latex_content = generate_latex(request.title, request.blocks, request.options)
    filename = _safe_filename(request.title, "tex")
    if raw:
        return Response(
            content=latex_content,
            media_type="application/x-latex",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return ExportResponse(
        filename=filename,
        mime_type="application/x-latex",
        format="latex",
        content=latex_content,
        size_bytes=len(latex_content.encode("utf-8")),
    )


@app.post("/export/docx")
def export_docx(request: ExportRequest, raw: bool = Query(default=False)):
    docx_bytes = generate_docx(request.title, request.blocks, request.options)
    filename = _safe_filename(request.title, "docx")
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if raw:
        return Response(
            content=docx_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # Codifica em base64 no JSON de resposta
    b64_content = base64.b64encode(docx_bytes).decode("ascii")
    return ExportResponse(
        filename=filename,
        mime_type=mime_type,
        format="docx",
        content=b64_content,
        size_bytes=len(docx_bytes),
    )


@app.post("/export/markdown")
def export_markdown(request: ExportRequest, raw: bool = Query(default=False)):
    md_content = generate_markdown(request.title, request.blocks, request.options)
    filename = _safe_filename(request.title, "md")
    if raw:
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    return ExportResponse(
        filename=filename,
        mime_type="text/markdown",
        format="markdown",
        content=md_content,
        size_bytes=len(md_content.encode("utf-8")),
    )


@app.post("/export/generate")
def export_generic(request: ExportRequest, raw: bool = Query(default=False)):
    """Roteador unificado para exportação em qualquer formato suportado."""
    fmt = request.format.lower()
    if fmt == "html":
        return export_html(request, raw=raw)
    elif fmt == "pdf":
        return export_pdf(request, raw=raw)
    elif fmt == "latex":
        return export_latex(request, raw=raw)
    elif fmt == "docx":
        return export_docx(request, raw=raw)
    elif fmt == "markdown":
        return export_markdown(request, raw=raw)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format: {request.format}",
        )
