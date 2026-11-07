import io
import math
import re
import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any, Generator, List, Optional, Tuple

import duckdb
import pyarrow as pa
import pyarrow.ipc as ipc
import sqlglot
from sqlglot import exp
from sqlglot.tokens import TokenType

from app.config import settings
from app.pii_masking import auto_detect_and_mask_pii
from app.schemas import ColumnMeta, QueryResult


class QueryEngineError(ValueError):
    """Erro em tempo de validação ou execução de consulta."""


def validate_sql(sql: str) -> str:
    """Valida que o SQL é exatamente uma instrução SELECT pura, sem funções de tabela proibidas."""
    if not sql or not sql.strip():
        raise QueryEngineError("SQL query cannot be empty")

    try:
        statements = [
            s for s in sqlglot.parse(sql, read="duckdb")
            if s is not None and not isinstance(s, exp.Semicolon)
        ]
    except sqlglot.errors.SqlglotError as exc:
        raise QueryEngineError(f"SQL syntax error: {str(exc).splitlines()[0]}") from exc

    if len(statements) != 1:
        raise QueryEngineError("Exactly one SQL statement is allowed")

    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise QueryEngineError("Only read-only SELECT queries are allowed")

    # Verifica se há DDL/DML ou comandos administrativos incorporados
    forbidden_types = (
        exp.Drop,
        exp.Delete,
        exp.Insert,
        exp.Update,
        exp.Alter,
        exp.Create,
        exp.Command,
    )
    for node in stmt.walk():
        if isinstance(node, forbidden_types):
            raise QueryEngineError(f"Forbidden SQL operation: {type(node).__name__}")

    # Rejeita chamadas a table functions como read_csv, read_parquet, range, system
    for table in stmt.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise QueryEngineError("Table functions (read_csv, read_parquet, range, etc.) are prohibited in query sandbox")

    return _strip_trailing_semicolons(sql)


def _strip_trailing_semicolons(sql: str) -> str:
    tokens = sqlglot.tokenize(sql, read="duckdb")
    while tokens and tokens[-1].token_type == TokenType.SEMICOLON:
        tokens.pop()
    if not tokens:
        return ""
    return sql[: tokens[-1].end + 1]


def _json_safe(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, dtime)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    return str(v)


def _infer_measurement_level(type_str: str) -> str:
    t = type_str.upper()
    if any(k in t for k in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL", "BIGINT")):
        return "scale"
    elif any(k in t for k in ("DATE", "TIME", "TIMESTAMP")):
        return "ordinal"
    return "nominal"


def _escape_sql_literal(s: str) -> str:
    escaped = s.replace("'", "''")
    return f"'{escaped}'"


def find_dataset_files(data_dir: str, tenant_id: str, dataset_id: Optional[str] = None) -> List[Tuple[str, Path]]:
    """Localiza arquivos Parquet acessíveis pelo tenant e devolve tuplas (table_name, Path)."""
    base = Path(data_dir)
    results = []
    seen_tables = set()

    search_dirs = [
        base / "tenants" / tenant_id / "datasets",
        base / "tenants" / tenant_id,
        base / "datasets",
        base,
    ]

    for d in search_dirs:
        if not d.exists() or not d.is_dir():
            continue
        for p in d.glob("*.parquet"):
            if not p.is_file():
                continue
            table_name = p.stem.replace("-", "_").replace(".", "_")
            if table_name not in seen_tables:
                seen_tables.add(table_name)
                results.append((table_name, p.resolve()))

    # Se dataset_id foi explicitado mas seu nome de arquivo diferir do stem
    if dataset_id:
        ds_stem = dataset_id.replace("-", "_").replace(".", "_")
        for d in search_dirs:
            p = d / f"{dataset_id}.parquet"
            if p.exists() and p.is_file():
                resolved = p.resolve()
                if "dataset" not in seen_tables:
                    results.append(("dataset", resolved))
                    seen_tables.add("dataset")
                if ds_stem not in seen_tables:
                    results.append((ds_stem, resolved))
                    seen_tables.add(ds_stem)
                break

    return results


def create_sandboxed_connection(
    data_dir: str,
    tenant_id: str,
    dataset_id: Optional[str] = None,
    extra_files: Optional[List[Tuple[str, Path]]] = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit={_escape_sql_literal(settings.query_memory_limit)}")
    con.execute(f"SET threads={int(settings.query_threads)}")

    files = find_dataset_files(data_dir, tenant_id, dataset_id)
    if extra_files:
        files.extend(extra_files)

    allowed_paths = []
    for table_name, p in files:
        p_str = str(p.resolve())
        allowed_paths.append(p_str)
        # Registra VIEW segura apontando para o Parquet
        con.execute(f'CREATE VIEW "{table_name}" AS SELECT * FROM read_parquet({_escape_sql_literal(p_str)})')

    if allowed_paths:
        con.execute("SET allowed_paths=[" + ",".join(_escape_sql_literal(p) for p in allowed_paths) + "]")
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    return con


def execute_query(
    sql: str,
    tenant_id: str = "default",
    dataset_id: Optional[str] = None,
    limit: Optional[int] = None,
    timeout_s: Optional[float] = None,
    mask_pii: bool = False,
    extra_files: Optional[List[Tuple[str, Path]]] = None,
) -> QueryResult:
    clean_sql = validate_sql(sql)
    row_limit = min(limit or settings.query_row_limit, settings.query_row_limit)
    timeout = timeout_s if timeout_s is not None else settings.query_timeout_s

    con = create_sandboxed_connection(settings.data_dir, tenant_id, dataset_id, extra_files)
    timed_out = threading.Event()

    def _interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(timeout, _interrupt)
    started = time.perf_counter()
    timer.start()

    try:
        wrapped_query = f"SELECT * FROM (\n{clean_sql}\n) AS q LIMIT {row_limit}"
        cur = con.execute(wrapped_query)
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

        exec_time_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=exec_time_ms,
        )
    except duckdb.Error as exc:
        if timed_out.is_set():
            raise QueryEngineError(f"Query exceeded execution time limit of {timeout:g}s") from exc
        raise QueryEngineError(f"{type(exc).__name__}: {str(exc).splitlines()[0]}") from exc
    finally:
        timer.cancel()
        con.close()


def execute_query_arrow_stream(
    sql: str,
    tenant_id: str = "default",
    dataset_id: Optional[str] = None,
    limit: Optional[int] = None,
    timeout_s: Optional[float] = None,
    extra_files: Optional[List[Tuple[str, Path]]] = None,
) -> bytes:
    clean_sql = validate_sql(sql)
    row_limit = min(limit or settings.query_row_limit, settings.query_row_limit)
    timeout = timeout_s if timeout_s is not None else settings.query_timeout_s

    con = create_sandboxed_connection(settings.data_dir, tenant_id, dataset_id, extra_files)
    timed_out = threading.Event()

    def _interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(timeout, _interrupt)
    timer.start()

    try:
        wrapped_query = f"SELECT * FROM (\n{clean_sql}\n) AS q LIMIT {row_limit}"
        arrow_table = con.sql(wrapped_query).to_arrow_table()

        sink = io.BytesIO()
        with ipc.new_stream(sink, arrow_table.schema) as writer:
            writer.write_table(arrow_table)
        return sink.getvalue()
    except duckdb.Error as exc:
        if timed_out.is_set():
            raise QueryEngineError(f"Query exceeded execution time limit of {timeout:g}s") from exc
        raise QueryEngineError(f"{type(exc).__name__}: {str(exc).splitlines()[0]}") from exc
    finally:
        timer.cancel()
        con.close()
