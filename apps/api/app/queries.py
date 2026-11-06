"""Execução de SQL do usuário, somente leitura e confinada.

Defesa em camadas:
  1. sqlglot: exatamente 1 statement, do tipo consulta, sem funções de tabela (read_csv(), range()…);
  2. DuckDB com `allowed_paths` = só os Parquets dos datasets, acesso externo desligado e
     configuração travada (não dá para reabrir, instalar extensões, ler outros arquivos ou usar COPY/ATTACH);
  3. limites de memória, linhas e tempo (interrupt por timer).
"""
import math
import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.tokens import TokenType

from . import auth, datasets, permissions
from .config import settings
from .schemas import Dataset, QueryColumn, QueryResult


class QueryError(ValueError):
    """Consulta inválida, proibida, expirada ou que falhou -> HTTP 422."""


def validate_sql(sql: str) -> str:
    """Valida e devolve o SQL original sem ';' final (não o regenerado, para não alterar a semântica)."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None and not isinstance(s, exp.Semicolon)]
    except sqlglot.errors.SqlglotError as exc:
        raise QueryError(f"SQL syntax error: {str(exc).splitlines()[0]}") from exc
    if len(statements) != 1:
        raise QueryError("exactly one SQL statement is allowed")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise QueryError("only read-only SELECT queries are allowed")
    for table in stmt.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise QueryError("table functions (read_csv, range, …) are not allowed; query a dataset table instead")
    return _strip_trailing_semicolons(sql)


def _strip_trailing_semicolons(sql: str) -> str:
    """Corta o SQL original no fim do último token que não seja ';' (descarta ';' e comentários finais)."""
    tokens = sqlglot.tokenize(sql, read="duckdb")
    while tokens and tokens[-1].token_type == TokenType.SEMICOLON:
        tokens.pop()
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


def _sandbox(views: list[tuple[Dataset, Path]], writable: list[Path] | None = None) -> duckdb.DuckDBPyConnection:
    """`views`: (dataset, Parquet a abrir) que o usuário pode ler; o resto não existe para ele.
    `writable`: arquivos extras liberados (a materialização de consulta grava SÓ o seu Parquet de destino)."""
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit={datasets.sql_str(settings.query_memory_limit)}")
    con.execute(f"SET threads={int(settings.query_threads)}")
    paths = []
    for ds, parquet in views:
        p = str(parquet.resolve())
        paths.append(p)
        con.execute(f'CREATE VIEW "{ds.table_name}" AS SELECT * FROM read_parquet({datasets.sql_str(p)})')
    paths += [str(w.resolve()) for w in (writable or [])]
    con.execute("SET allowed_paths=[" + ",".join(datasets.sql_str(p) for p in paths) + "]")
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    return con


def run_query(sql: str, limit: int | None = None, timeout_s: float | None = None, *, user: auth.User) -> QueryResult:
    clean = validate_sql(sql)
    row_limit = min(limit or settings.query_row_limit, settings.query_row_limit)
    timeout = timeout_s if timeout_s is not None else settings.query_timeout_s

    con = _sandbox(permissions.visible_views(user))
    timed_out = threading.Event()

    def _interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(timeout, _interrupt)
    started = time.perf_counter()
    timer.start()
    try:
        # \n antes do ')' evita que um comentário '--' no fim do SQL engula o fechamento
        cur = con.execute(f"SELECT * FROM (\n{clean}\n) AS q LIMIT {row_limit + 1}")
        columns = [QueryColumn(name=d[0], dtype=str(d[1])) for d in cur.description]
        fetched = cur.fetchall()
    except duckdb.Error as exc:
        if timed_out.is_set():
            raise QueryError(f"query exceeded the {timeout:g}s time limit") from exc
        raise QueryError(f"{type(exc).__name__}: {str(exc).splitlines()[0]}") from exc
    finally:
        timer.cancel()
        con.close()

    truncated = len(fetched) > row_limit
    rows = [[_json_safe(v) for v in r] for r in fetched[:row_limit]]
    return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated,
                       elapsed_ms=int((time.perf_counter() - started) * 1000))
