import re
from typing import Any


def _escape_latex(text: str) -> str:
    """Escapa caracteres especiais do LaTeX fora de blocos matemáticos."""
    conv = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    regex = re.compile("|".join(re.escape(k) for k in conv.keys()))
    return regex.sub(lambda match: conv[match.group(0)], text)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or content.get("markdown") or content.get("content") or ""
    return str(content or "")


def generate_latex(title: str, blocks: list[dict[str, Any]], options: dict[str, Any] | None = None) -> str:
    """
    Gera documento LaTeX acadêmico profissional compilável com o pacote booktabs,
    amsmath, geometry e suporte a tabelas APA 7th.
    """
    options = options or {}
    author = options.get("author", "MetaStatistic Platform")
    date = options.get("date", r"\today")

    body_chunks = []
    table_idx = 0

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
            safe_text = _escape_latex(text)
            if level == 1:
                body_chunks.append(f"\n\\section{{{safe_text}}}\n")
            elif level == 2:
                body_chunks.append(f"\n\\subsection{{{safe_text}}}\n")
            elif level == 3:
                body_chunks.append(f"\n\\subsubsection{{{safe_text}}}\n")
            else:
                body_chunks.append(f"\n\\paragraph{{{safe_text}}}\n")

        elif b_type == "text":
            raw_text = _extract_text(content)
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            for p in paragraphs:
                body_chunks.append(f"{_escape_latex(p)}\n\n")

        elif b_type == "equation":
            eq = _extract_text(content).strip()
            # Remove delimitadores $$ se existirem
            eq = re.sub(r"^\$\$|\$\$$", "", eq).strip()
            body_chunks.append(f"\\begin{{equation}}\n{eq}\n\\end{{equation}}\n\n")

        elif b_type == "table_apa":
            table_idx += 1
            caption = f"Analytical Findings {table_idx}"
            headers = []
            rows = []
            note = ""

            if isinstance(content, dict):
                caption = content.get("caption") or content.get("title") or caption
                headers = content.get("headers", [])
                rows = content.get("rows", [])
                note = content.get("note", "")

            col_count = max(len(headers), max((len(r) for r in rows), default=1))
            col_spec = "l" + "r" * (col_count - 1)

            header_str = " & ".join(_escape_latex(str(h)) for h in headers) + r" \\" if headers else ""
            row_lines = []
            for r in rows:
                row_lines.append(" & ".join(_escape_latex(str(cell)) for cell in r) + r" \\")
            rows_str = "\n".join(row_lines)

            note_str = f"\\par\\vspace{{2pt}}\\footnotesize{{\\textit{{Note.}} {_escape_latex(note)}}}" if note else ""

            table_latex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{{_escape_latex(caption)}}}
\\begin{{tabular}}{{{col_spec}}}
\\toprule
{header_str}
\\midrule
{rows_str}
\\bottomrule
\\end{{tabular}}
{note_str}
\\end{{table}}
"""
            body_chunks.append(table_latex + "\n")

        elif b_type == "callout":
            text = _extract_text(content)
            body_chunks.append(
                f"\\begin{{quote}}\n\\textbf{{Note:}} {_escape_latex(text)}\n\\end{{quote}}\n\n"
            )

        elif b_type == "kpi":
            label = "KPI"
            value = "-"
            if isinstance(content, dict):
                label = content.get("label", "KPI")
                value = str(content.get("value", "-"))
            body_chunks.append(
                f"\\textbf{{{_escape_latex(label)}}}: \\texttt{{{_escape_latex(value)}}}\n\n"
            )

        elif b_type == "chart":
            title_chart = "Figure"
            if isinstance(content, dict):
                title_chart = content.get("title", title_chart)
            body_chunks.append(
                f"\\begin{{figure}}[htbp]\n\\centering\n% [Chart: {_escape_latex(title_chart)}]\n\\caption{{{_escape_latex(title_chart)}}}\n\\end{{figure}}\n\n"
            )

        else:
            text = _extract_text(content)
            body_chunks.append(f"{_escape_latex(text)}\n\n")

    content_str = "".join(body_chunks)

    latex_doc = f"""\\documentclass[12pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[margin=2.5cm]{{geometry}}
\\usepackage{{amsmath}}
\\usepackage{{amsfonts}}
\\usepackage{{booktabs}}
\\usepackage{{graphicx}}
\\usepackage{{caption}}
\\usepackage{{hyperref}}

\\title{{{_escape_latex(title)}}}
\\author{{{_escape_latex(author)}}}
\\date{{{date}}}

\\begin{{document}}
\\maketitle

{content_str}
\\end{{document}}
"""
    return latex_doc
