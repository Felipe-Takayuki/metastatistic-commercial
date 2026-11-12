import html
from typing import Any


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or content.get("markdown") or content.get("content") or ""
    return str(content or "")


def generate_html(title: str, blocks: list[dict[str, Any]], options: dict[str, Any] | None = None) -> str:
    """
    Gera documento HTML editorial com tipografia acadêmica conforme normas APA 7th
    e regras de CSS Paged Media para impressão e conversão direta para PDF.
    """
    options = options or {}
    author = options.get("author", "MetaStatistic Research Engine")
    institution = options.get("institution", "MetaStatistic Platform")
    is_pdf_mode = options.get("pdf_mode", False)

    body_elements = []
    table_count = 0
    figure_count = 0

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
            level = max(1, min(level, 4))
            css_class = f"apa-heading-{level}"
            body_elements.append(
                f'<h{level} class="{css_class}">{html.escape(text)}</h{level}>'
            )

        elif b_type == "text":
            text = _extract_text(content)
            # Converte parágrafos simples
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [text] if text else []
            for p in paragraphs:
                body_elements.append(f'<p class="apa-paragraph">{html.escape(p)}</p>')

        elif b_type == "callout":
            callout_type = "info"
            text = ""
            if isinstance(content, dict):
                callout_type = content.get("type", "info")
                text = content.get("text", "")
            else:
                text = str(content)
            body_elements.append(
                f'<div class="apa-callout apa-callout-{html.escape(callout_type)}">'
                f'<p>{html.escape(text)}</p></div>'
            )

        elif b_type == "kpi":
            label = "KPI"
            value = "-"
            delta = ""
            if isinstance(content, dict):
                label = content.get("label", "Metric")
                value = str(content.get("value", "-"))
                delta = str(content.get("delta", ""))
            delta_html = f'<span class="kpi-delta">{html.escape(delta)}</span>' if delta else ""
            body_elements.append(
                f'<div class="kpi-card">'
                f'<div class="kpi-label">{html.escape(label)}</div>'
                f'<div class="kpi-value">{html.escape(value)} {delta_html}</div>'
                f'</div>'
            )

        elif b_type == "equation":
            eq = _extract_text(content)
            body_elements.append(
                f'<div class="apa-equation">'
                f'<code>$$ {html.escape(eq)} $$</code>'
                f'</div>'
            )

        elif b_type == "table_apa":
            table_count += 1
            caption = f"Table {table_count}"
            table_title = "Analytical Results"
            headers = []
            rows = []
            note = ""

            if isinstance(content, dict):
                caption = content.get("caption", caption)
                table_title = content.get("title", table_title)
                headers = content.get("headers", [])
                rows = content.get("rows", [])
                note = content.get("note", "")

            th_html = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
            tr_list = []
            for row in rows:
                tds = "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row)
                tr_list.append(f"<tr>{tds}</tr>")
            tbody_html = "\n".join(tr_list)

            note_html = f'<p class="apa-table-note"><em>Note.</em> {html.escape(note)}</p>' if note else ""

            body_elements.append(
                f'<div class="apa-table-container">'
                f'<p class="apa-table-number">Table {table_count}</p>'
                f'<p class="apa-table-title">{html.escape(caption or table_title)}</p>'
                f'<table class="apa-table">'
                f'<thead><tr>{th_html}</tr></thead>'
                f'<tbody>{tbody_html}</tbody>'
                f'</table>'
                f'{note_html}'
                f'</div>'
            )

        elif b_type == "chart":
            figure_count += 1
            chart_title = f"Figure {figure_count}"
            img_src = ""
            desc = ""
            if isinstance(content, dict):
                chart_title = content.get("title", chart_title)
                img_src = content.get("image_url", "")
                desc = content.get("description", "")
            img_html = f'<img src="{html.escape(img_src)}" alt="{html.escape(chart_title)}" class="chart-img"/>' if img_src else '<div class="chart-placeholder">[Interactive Data Visualization]</div>'
            body_elements.append(
                f'<div class="apa-figure-container">'
                f'{img_html}'
                f'<p class="apa-figure-caption"><em>Figure {figure_count}.</em> {html.escape(chart_title)}. {html.escape(desc)}</p>'
                f'</div>'
            )

        else:
            text = _extract_text(content)
            body_elements.append(f'<div class="apa-generic-block">{html.escape(text)}</div>')

    rendered_body = "\n".join(body_elements)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <style>
    @page {{
      size: A4;
      margin: 2.5cm;
      @bottom-right {{
        content: counter(page);
        font-family: 'Times New Roman', Times, serif;
        font-size: 10pt;
      }}
      @top-left {{
        content: '{html.escape(title[:40])}';
        font-family: 'Times New Roman', Times, serif;
        font-size: 9pt;
        text-transform: uppercase;
        color: #555;
      }}
    }}

    body {{
      font-family: 'Times New Roman', Times, Georgia, serif;
      font-size: 12pt;
      line-height: 2.0;
      color: #111;
      max-width: 800px;
      margin: 0 auto;
      padding: 2cm 1.5cm;
      background: #fff;
    }}

    .apa-header-page {{
      text-align: center;
      margin-bottom: 3rem;
      page-break-after: always;
    }}

    .apa-title {{
      font-size: 18pt;
      font-weight: bold;
      margin-top: 5rem;
      margin-bottom: 2rem;
      line-height: 1.4;
    }}

    .apa-author {{
      font-size: 12pt;
      margin-bottom: 0.5rem;
    }}

    .apa-institution {{
      font-size: 11pt;
      color: #333;
    }}

    .apa-heading-1 {{
      font-size: 14pt;
      font-weight: bold;
      text-align: center;
      margin-top: 2rem;
      margin-bottom: 1rem;
      page-break-after: avoid;
    }}

    .apa-heading-2 {{
      font-size: 13pt;
      font-weight: bold;
      text-align: left;
      margin-top: 1.5rem;
      margin-bottom: 0.75rem;
      page-break-after: avoid;
    }}

    .apa-heading-3 {{
      font-size: 12pt;
      font-weight: bold;
      font-style: italic;
      text-align: left;
      margin-top: 1.25rem;
      margin-bottom: 0.5rem;
      page-break-after: avoid;
    }}

    .apa-paragraph {{
      text-indent: 0.5in;
      margin-bottom: 1rem;
      text-align: justify;
    }}

    /* APA 7th Table Styling: Strict horizontal borders only */
    .apa-table-container {{
      margin: 2rem 0;
      page-break-inside: avoid;
    }}

    .apa-table-number {{
      font-weight: bold;
      margin-bottom: 0.2rem;
      text-indent: 0;
    }}

    .apa-table-title {{
      font-style: italic;
      margin-bottom: 0.5rem;
      text-indent: 0;
    }}

    .apa-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 10.5pt;
      line-height: 1.5;
      border-top: 2px solid #000;
      border-bottom: 2px solid #000;
      margin-bottom: 0.5rem;
    }}

    .apa-table th {{
      border-bottom: 1px solid #000;
      padding: 6px 12px;
      font-weight: bold;
      text-align: left;
    }}

    .apa-table td {{
      padding: 6px 12px;
      border: none;
    }}

    .apa-table-note {{
      font-size: 9.5pt;
      line-height: 1.3;
      margin-top: 0.4rem;
      text-indent: 0;
      color: #222;
    }}

    .apa-figure-container {{
      margin: 2rem 0;
      text-align: center;
      page-break-inside: avoid;
    }}

    .chart-img {{
      max-width: 100%;
      height: auto;
      border-radius: 4px;
    }}

    .chart-placeholder {{
      border: 1px dashed #999;
      padding: 2rem;
      background: #fafafa;
      color: #666;
      font-family: sans-serif;
    }}

    .apa-figure-caption {{
      font-size: 10pt;
      line-height: 1.4;
      text-align: left;
      margin-top: 0.5rem;
      text-indent: 0;
    }}

    .apa-equation {{
      text-align: center;
      margin: 1.5rem 0;
      font-family: 'Courier New', Courier, monospace;
      background: #fdfdfd;
      padding: 0.5rem;
    }}

    .apa-callout {{
      border-left: 4px solid #0284c7;
      background-color: #f0f9ff;
      padding: 1rem 1.5rem;
      margin: 1.5rem 0;
      font-family: sans-serif;
      font-size: 10.5pt;
      line-height: 1.6;
    }}

    .apa-callout p {{
      margin: 0;
      text-indent: 0;
    }}

    .kpi-card {{
      display: inline-block;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 1rem 1.5rem;
      margin: 0.5rem;
      background: #f8fafc;
      font-family: sans-serif;
    }}

    .kpi-label {{
      font-size: 9pt;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .kpi-value {{
      font-size: 18pt;
      font-weight: bold;
      color: #0f172a;
    }}

    .kpi-delta {{
      font-size: 10pt;
      color: #16a34a;
      margin-left: 0.5rem;
    }}

    @media print {{
      body {{
        padding: 0;
        max-width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <div class="apa-header-page">
    <div class="apa-title">{html.escape(title)}</div>
    <div class="apa-author">{html.escape(author)}</div>
    <div class="apa-institution">{html.escape(institution)}</div>
  </div>

  <div class="apa-content">
{rendered_body}
  </div>
</body>
</html>
"""
    return html_template
