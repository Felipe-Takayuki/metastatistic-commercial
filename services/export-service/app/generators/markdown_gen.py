from typing import Any


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text") or content.get("markdown") or content.get("content") or ""
    return str(content or "")


def generate_markdown(title: str, blocks: list[dict[str, Any]], options: dict[str, Any] | None = None) -> str:
    """
    Gera documento Markdown no padrão GitHub Flavored Markdown (GFM)
    com suporte a equações KaTeX e formatação de tabelas estruturadas.
    """
    options = options or {}
    lines = [f"# {title}\n"]

    table_num = 0

    for block in blocks:
        b_type = block.get("type", "text")
        content = block.get("content", "")

        if b_type == "heading":
            level = 2
            text = ""
            if isinstance(content, dict):
                level = content.get("level", 2)
                text = content.get("text", "")
            else:
                text = str(content)
            hashes = "#" * max(1, min(level, 6))
            lines.append(f"{hashes} {text}\n")

        elif b_type == "text":
            raw_text = _extract_text(content)
            lines.append(f"{raw_text}\n")

        elif b_type == "equation":
            eq = _extract_text(content).strip()
            lines.append(f"$$\n{eq}\n$$\n")

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

            lines.append(f"**Table {table_num}.** *{caption}*\n")

            if headers:
                header_line = "| " + " | ".join(str(h) for h in headers) + " |"
                separator_line = "| " + " | ".join("---" for _ in headers) + " |"
                lines.append(header_line)
                lines.append(separator_line)
            elif rows:
                col_count = len(rows[0])
                header_line = "| " + " | ".join(f"Col {i+1}" for i in range(col_count)) + " |"
                separator_line = "| " + " | ".join("---" for _ in range(col_count)) + " |"
                lines.append(header_line)
                lines.append(separator_line)

            for r in rows:
                row_line = "| " + " | ".join(str(cell) for cell in r) + " |"
                lines.append(row_line)

            if note:
                lines.append(f"\n*Note.* {note}\n")
            else:
                lines.append("")

        elif b_type == "callout":
            text = _extract_text(content)
            lines.append(f"> **Note:** {text}\n")

        elif b_type == "kpi":
            label = "KPI"
            value = "-"
            delta = ""
            if isinstance(content, dict):
                label = content.get("label", "KPI")
                value = str(content.get("value", "-"))
                delta = str(content.get("delta", ""))
            delta_str = f" ({delta})" if delta else ""
            lines.append(f"> **{label}:** `{value}`{delta_str}\n")

        elif b_type == "chart":
            title_chart = "Visualization"
            img_url = ""
            if isinstance(content, dict):
                title_chart = content.get("title", title_chart)
                img_url = content.get("image_url", "")
            if img_url:
                lines.append(f"![{title_chart}]({img_url})\n")
            else:
                lines.append(f"*Chart: {title_chart}*\n")

        else:
            lines.append(f"{_extract_text(content)}\n")

    return "\n".join(lines)
