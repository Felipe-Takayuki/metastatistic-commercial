"""Salvar o resultado de uma consulta SQL como dataset (ex.: criar a coluna `bloco`, aplicar sqrt/log10).

Mesma segurança de /queries/run: a consulta é validada (1 statement, só leitura, sem funções de tabela) e roda no
sandbox do DuckDB. A única diferença é que o sandbox ganha permissão de escrita para UM arquivo: o Parquet de destino.
"""
import threading
import uuid

import duckdb

from . import datasets, queries
from .config import settings
from .schemas import Dataset


def create_dataset_from_query(name: str, sql: str) -> Dataset:
    name = name.strip()
    if not name:
        raise datasets.DatasetError("dataset name must not be blank")
    clean = queries.validate_sql(sql)  # QueryError (-> 422) se não for uma consulta somente leitura
    dataset_id = uuid.uuid4().hex
    out = datasets.parquet_path(dataset_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    max_rows = settings.derived_dataset_max_rows

    con = queries._sandbox(datasets.list_datasets(), writable=[out])
    timed_out = threading.Event()
    timer = threading.Timer(settings.derived_dataset_timeout_s, lambda: (timed_out.set(), con.interrupt()))
    timer.start()
    try:
        # +1 linha: se vier a mais, o dataset estouraria o limite (detectado abaixo, em vez de truncar em silêncio)
        con.execute(
            f"COPY (SELECT * FROM (\n{clean}\n) AS q LIMIT {max_rows + 1}) "
            f"TO {datasets.sql_str(str(out))} (FORMAT parquet, COMPRESSION zstd)"
        )
    except duckdb.Error as exc:
        out.unlink(missing_ok=True)
        if timed_out.is_set():
            raise queries.QueryError(f"query exceeded the {settings.derived_dataset_timeout_s:g}s time limit") from exc
        raise queries.QueryError(f"{type(exc).__name__}: {str(exc).splitlines()[0]}") from exc
    finally:
        timer.cancel()
        con.close()

    try:
        if not out.exists():
            raise datasets.DatasetError("the query produced no output")
        n_rows, columns = datasets.describe_parquet(out)
        if n_rows == 0 or not columns:
            raise datasets.DatasetError("the query returned no rows, so there is nothing to save")
        if n_rows > max_rows:
            raise datasets.DatasetError(f"the result has more than {max_rows:,} rows; filter or aggregate it first")
        return datasets.register(dataset_id, name, n_rows, columns)
    except Exception:
        out.unlink(missing_ok=True)  # nunca deixa um Parquet órfão sem registro
        raise
