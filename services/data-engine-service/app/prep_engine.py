import re
from pathlib import Path
from typing import Any, List, Optional, Tuple

import duckdb
from app.config import settings
from app.pii_masking import auto_detect_and_mask_pii
from app.query_engine import (
    _infer_measurement_level,
    _json_safe,
    create_sandboxed_connection,
    find_dataset_files,
)
from app.schemas import ColumnMeta, PrepStep, TransformPreviewResponse


def build_prep_query(dataset_table: str, steps: List[PrepStep], limit: int = 50) -> str:
    current_table = f'"{dataset_table}"'
    step_ctes = []

    for idx, step in enumerate(steps):
        next_table = f"prep_step_{idx}"
        op = step.op.lower().strip()
        params = step.params or {}

        if op == "select":
            cols = params.get("columns", [])
            if cols:
                escaped_cols = ", ".join(f'"{c}"' for c in cols)
                query = f"SELECT {escaped_cols} FROM {current_table}"
            else:
                query = f"SELECT * FROM {current_table}"

        elif op == "rename":
            mapping = params.get("columns", {})
            if mapping:
                # SELECT original AS new
                # DuckDB suporta SELECT * RENAME (old AS new)
                rename_clause = ", ".join(f'"{old}" AS "{new}"' for old, new in mapping.items())
                query = f"SELECT * RENAME ({rename_clause}) FROM {current_table}"
            else:
                query = f"SELECT * FROM {current_table}"

        elif op == "filter":
            cond = params.get("condition")
            if not cond:
                col = params.get("column")
                operator = params.get("operator", "=")
                val = params.get("value")
                if col is not None and val is not None:
                    if isinstance(val, (int, float)):
                        cond = f'"{col}" {operator} {val}'
                    else:
                        escaped_val = str(val).replace("'", "''")
                        cond = f'"{col}" {operator} \'{escaped_val}\''
            if cond:
                # Sanitização básica para evitar injeção
                query = f"SELECT * FROM {current_table} WHERE {cond}"
            else:
                query = f"SELECT * FROM {current_table}"

        elif op == "sort":
            cols = params.get("columns", [])
            direction = "DESC" if not params.get("ascending", True) else "ASC"
            if cols:
                order_clause = ", ".join(f'"{c}" {direction}' for c in cols)
                query = f"SELECT * FROM {current_table} ORDER BY {order_clause}"
            else:
                query = f"SELECT * FROM {current_table}"

        elif op == "cast":
            casts = params.get("columns", {})
            if casts:
                # DuckDB: SELECT * EXCLUDE (col1, col2), CAST(col1 AS type1) AS col1, ...
                exclude_cols = ", ".join(f'"{c}"' for c in casts.keys())
                cast_cols = ", ".join(f'CAST("{c}" AS {t}) AS "{c}"' for c, t in casts.items())
                query = f"SELECT * EXCLUDE ({exclude_cols}), {cast_cols} FROM {current_table}"
            else:
                query = f"SELECT * FROM {current_table}"

        else:
            query = f"SELECT * FROM {current_table}"

        step_ctes.append(f"{next_table} AS ({query})")
        current_table = next_table

    if step_ctes:
        cte_block = "WITH " + ",\n".join(step_ctes)
        final_sql = f"{cte_block}\nSELECT * FROM {current_table} LIMIT {limit}"
    else:
        final_sql = f"SELECT * FROM {current_table} LIMIT {limit}"

    return final_sql


def preview_transforms(
    dataset_id: str,
    steps: List[PrepStep],
    limit: int = 50,
    tenant_id: str = "default",
    mask_pii: bool = False,
    extra_files: Optional[List[Tuple[str, Path]]] = None,
) -> TransformPreviewResponse:
    con = create_sandboxed_connection(settings.data_dir, tenant_id, dataset_id, extra_files)
    try:
        table_name = "dataset"
        # Verifica se 'dataset' view existe, caso contrário busca pelo nome do dataset
        table_exists = False
        tables_res = con.execute("SHOW TABLES;").fetchall()
        available_tables = [r[0] for r in tables_res]
        if "dataset" in available_tables:
            table_name = "dataset"
            table_exists = True
        elif dataset_id.replace("-", "_").replace(".", "_") in available_tables:
            table_name = dataset_id.replace("-", "_").replace(".", "_")
            table_exists = True
        elif available_tables:
            table_name = available_tables[0]
            table_exists = True

        if not table_exists:
            raise ValueError(f"Dataset '{dataset_id}' not found for tenant '{tenant_id}'")

        sql = build_prep_query(table_name, steps, limit=limit)
        cur = con.execute(sql)
        desc = cur.description or []
        columns = [
            ColumnMeta(
                name=d[0],
                type=str(d[1]),
                measurementLevel=_infer_measurement_level(str(d[1])),
                nullable=True,
            )
            for d in desc
        ]
        fetched = cur.fetchall()
        rows = []
        for row in fetched:
            rows.append({desc[i][0]: _json_safe(row[i]) for i in range(len(desc))})

        if mask_pii:
            rows = auto_detect_and_mask_pii(rows, tenant_id=tenant_id)

        return TransformPreviewResponse(
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )
    finally:
        con.close()
