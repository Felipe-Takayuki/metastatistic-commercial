import io
from typing import Any
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or content.get("markdown") or content.get("content") or ""
    return str(content or "")


def generate_docx(title: str, blocks: list[dict[str, Any]], options: dict[str, Any] | None = None) -> bytes:
    """
    Gera binário DOCX formatado com tipografia editorial e tabelas APA 7th.
    """
    options = options or {}
    author = options.get("author", "MetaStatistic Platform")

    doc = docx.Document()

    # Define margens A4
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Título Principal
    title_p = doc.add_heading(level=0)
    title_run = title_p.add_run(title)
    title_run.font.name = "Times New Roman"
    title_run.font.size = Pt(20)
    title_run.font.bold = True
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Autor / Metadados
    author_p = doc.add_paragraph()
    author_run = author_p.add_run(f"Prepared by: {author}")
    author_run.font.name = "Times New Roman"
    author_run.font.size = Pt(11)
    author_run.font.italic = True
    author_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()

    table_num = 0

    for block in blocks:
        b_type = block.get("type", "text")
        content = block.get("content", "")

        if b_type == "heading":
            level = 1
            text = ""
            if isinstance(content, dict):
                level = content.get("level", 1)
                text = content.get("text", "")
            else:
                text = str(content)
            h = doc.add_heading(text, level=min(level, 3))
            h.paragraph_format.space_before = Pt(14)
            h.paragraph_format.space_after = Pt(6)

        elif b_type == "text":
            raw_text = _extract_text(content)
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            for p in paragraphs:
                p_elem = doc.add_paragraph()
                p_elem.paragraph_format.first_line_indent = Inches(0.5)
                p_elem.paragraph_format.line_spacing = 1.5
                run = p_elem.add_run(p)
                run.font.name = "Times New Roman"
                run.font.size = Pt(12)

        elif b_type == "table_apa":
            table_num += 1
            caption = f"Table {table_num}"
            headers = []
            rows = []
            note = ""

            if isinstance(content, dict):
                caption = content.get("caption") or content.get("title") or caption
                headers = content.get("headers", [])
                rows = content.get("rows", [])
                note = content.get("note", "")

            # Cabeçalho da tabela APA
            num_p = doc.add_paragraph()
            num_p.paragraph_format.space_before = Pt(12)
            num_p.paragraph_format.space_after = Pt(2)
            run_num = num_p.add_run(f"Table {table_num}")
            run_num.bold = True
            run_num.font.name = "Times New Roman"

            title_p = doc.add_paragraph()
            title_p.paragraph_format.space_after = Pt(6)
            run_title = title_p.add_run(caption)
            run_title.italic = True
            run_title.font.name = "Times New Roman"

            col_count = max(len(headers), max((len(r) for r in rows), default=1))
            total_rows = (1 if headers else 0) + len(rows)

            table = doc.add_table(rows=total_rows, cols=col_count)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True

            curr_row = 0
            if headers:
                hdr_cells = table.rows[curr_row].cells
                for idx, h_text in enumerate(headers):
                    if idx < col_count:
                        hdr_cells[idx].text = str(h_text)
                        for r in hdr_cells[idx].paragraphs[0].runs:
                            r.font.bold = True
                            r.font.name = "Times New Roman"
                            r.font.size = Pt(10.5)
                curr_row += 1

            for r_data in rows:
                row_cells = table.rows[curr_row].cells
                for idx, cell_val in enumerate(r_data):
                    if idx < col_count:
                        row_cells[idx].text = str(cell_val)
                        for r in row_cells[idx].paragraphs[0].runs:
                            r.font.name = "Times New Roman"
                            r.font.size = Pt(10)
                curr_row += 1

            if note:
                note_p = doc.add_paragraph()
                note_p.paragraph_format.space_before = Pt(4)
                note_p.paragraph_format.space_after = Pt(12)
                run_note_lbl = note_p.add_run("Note. ")
                run_note_lbl.italic = True
                run_note_lbl.font.size = Pt(9.5)
                run_note_txt = note_p.add_run(note)
                run_note_txt.font.size = Pt(9.5)

        elif b_type == "equation":
            eq = _extract_text(content)
            eq_p = doc.add_paragraph()
            eq_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            eq_p.paragraph_format.space_before = Pt(8)
            eq_p.paragraph_format.space_after = Pt(8)
            eq_run = eq_p.add_run(eq)
            eq_run.font.name = "Consolas"
            eq_run.font.size = Pt(11)

        elif b_type == "callout":
            text = _extract_text(content)
            callout_p = doc.add_paragraph()
            callout_p.paragraph_format.left_indent = Inches(0.5)
            callout_p.paragraph_format.space_before = Pt(8)
            callout_p.paragraph_format.space_after = Pt(8)
            lbl_run = callout_p.add_run("Notice: ")
            lbl_run.bold = True
            c_run = callout_p.add_run(text)
            c_run.italic = True

        elif b_type == "kpi":
            label = "Metric"
            value = "-"
            if isinstance(content, dict):
                label = content.get("label", "Metric")
                value = str(content.get("value", "-"))
            kpi_p = doc.add_paragraph()
            kpi_p.paragraph_format.space_before = Pt(6)
            kpi_p.paragraph_format.space_after = Pt(6)
            l_run = kpi_p.add_run(f"{label}: ")
            l_run.bold = True
            v_run = kpi_p.add_run(value)
            v_run.font.name = "Consolas"

        elif b_type == "chart":
            title_chart = "Figure"
            if isinstance(content, dict):
                title_chart = content.get("title", title_chart)
            ch_p = doc.add_paragraph()
            ch_p.paragraph_format.space_before = Pt(10)
            ch_p.paragraph_format.space_after = Pt(4)
            ch_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_c = ch_p.add_run(f"[Chart / Visualization: {title_chart}]")
            r_c.italic = True

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
