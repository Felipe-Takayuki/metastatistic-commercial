import base64
import io
import docx
import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLE_PAYLOAD = {
    "title": "Clinical Trial Efficacy Evaluation",
    "blocks": [
        {
            "id": "h1",
            "type": "heading",
            "content": {"level": 1, "text": "Executive Results"},
        },
        {
            "id": "t1",
            "type": "text",
            "content": "The study evaluated 102 subjects across two study arms.",
        },
        {
            "id": "tbl1",
            "type": "table_apa",
            "content": {
                "caption": "Primary Clinical Endpoints by Group",
                "headers": ["Cohort", "N", "Mean (SD)", "t-statistic", "p-value"],
                "rows": [
                    ["Placebo", 50, "4.21 (1.10)", "-", "-"],
                    ["Active Drug", 52, "6.85 (0.95)", "12.87", "< .001"],
                ],
                "note": "All statistical tests were two-tailed.",
            },
        },
        {
            "id": "eq1",
            "type": "equation",
            "content": r"t = \frac{\bar{X}_1 - \bar{X}_2}{s_p \sqrt{\frac{2}{n}}}",
        },
        {
            "id": "k1",
            "type": "kpi",
            "content": {"label": "Effect Size (Cohen d)", "value": "1.82", "delta": "+0.45"},
        },
        {
            "id": "c1",
            "type": "callout",
            "content": {"type": "warning", "text": "Interim analysis data subject to audit."},
        },
    ],
    "options": {
        "author": "Clinical Biostatistics Core",
        "institution": "University Health Consortium",
    },
}


def test_health_check():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "export-service"


def test_export_html_apa():
    client = TestClient(app)
    resp = client.post("/export/html", json=SAMPLE_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "html"
    assert data["mime_type"] == "text/html"
    html_content = data["content"]

    # Valida presença de elementos APA 7th e CSS Paged Media
    assert "@page" in html_content
    assert "margin: 2.5cm" in html_content
    assert "apa-table" in html_content
    assert "Primary Clinical Endpoints by Group" in html_content
    assert "All statistical tests were two-tailed." in html_content
    assert "Clinical Trial Efficacy Evaluation" in html_content


def test_export_latex_booktabs():
    client = TestClient(app)
    payload = dict(SAMPLE_PAYLOAD)
    payload["format"] = "latex"
    resp = client.post("/export/latex", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "latex"
    tex_content = data["content"]

    # Valida estrutura LaTeX
    assert r"\documentclass[12pt,a4paper]{article}" in tex_content
    assert r"\usepackage{booktabs}" in tex_content
    assert r"\usepackage{amsmath}" in tex_content
    assert r"\begin{table}[htbp]" in tex_content
    assert r"\toprule" in tex_content
    assert r"\midrule" in tex_content
    assert r"\bottomrule" in tex_content
    assert r"\begin{equation}" in tex_content
    assert r"\section{Executive Results}" in tex_content


def test_export_docx_valid_binary():
    client = TestClient(app)
    payload = dict(SAMPLE_PAYLOAD)
    payload["format"] = "docx"

    # 1. Teste JSON com base64
    resp = client.post("/export/docx", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "docx"
    b64_str = data["content"]
    docx_bytes = base64.b64decode(b64_str)

    # Verifica se abre como documento DOCX válido
    doc = docx.Document(io.BytesIO(docx_bytes))
    paragraphs = [p.text for p in doc.paragraphs]
    assert any("Clinical Trial Efficacy Evaluation" in p for p in paragraphs)
    assert len(doc.tables) >= 1
    # Valida conteúdo da tabela
    table = doc.tables[0]
    cell_texts = [cell.text for row in table.rows for cell in row.cells]
    assert "Active Drug" in cell_texts

    # 2. Teste com raw=true (download direto)
    resp_raw = client.post("/export/docx?raw=true", json=payload)
    assert resp_raw.status_code == 200
    assert resp_raw.headers["content-type"].startswith("application/vnd.openxmlformats")
    doc_raw = docx.Document(io.BytesIO(resp_raw.content))
    assert len(doc_raw.tables) >= 1


def test_export_markdown_gfm():
    client = TestClient(app)
    payload = dict(SAMPLE_PAYLOAD)
    payload["format"] = "markdown"
    resp = client.post("/export/markdown", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "markdown"
    md_content = data["content"]

    assert "# Clinical Trial Efficacy Evaluation" in md_content
    assert "| Cohort | N | Mean (SD) |" in md_content
    assert "| --- |" in md_content
    assert "| Active Drug | 52 | 6.85 (0.95) |" in md_content
    assert "$$\nt =" in md_content


def test_export_generate_unified_router():
    client = TestClient(app)
    for fmt in ["html", "pdf", "latex", "docx", "markdown"]:
        req = dict(SAMPLE_PAYLOAD)
        req["format"] = fmt
        resp = client.post("/export/generate", json=req)
        assert resp.status_code == 200
        assert resp.json()["format"] == fmt

    # Teste de formato inválido
    bad_req = dict(SAMPLE_PAYLOAD)
    bad_req["format"] = "xyz"
    # Pydantic valida ou rota rejeita
    resp_bad = client.post("/export/generate", json=bad_req)
    assert resp_bad.status_code in {400, 422}
