"""Registro e ingestão de datasets: CSV -> Parquet (via DuckDB) + metadados em SQLite."""
import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import db
from .config import settings
from .schemas import Column, Dataset


class DatasetError(ValueError):
    """Erro do pedido (arquivo inválido, dataset inexistente…) -> HTTP 4xx."""


class DatasetNotFound(DatasetError):
    pass


_INT_TYPES = {"TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT"}
_FLOAT_TYPES = {"FLOAT", "DOUBLE", "REAL", "DECIMAL"}  # contagem de distintos não é informativa
_NUM_TYPES = _INT_TYPES | {"FLOAT", "DOUBLE", "REAL"}
ORDINAL_MAX_LEVELS = 10  # inteiros com poucos valores distintos (ex.: Likert) começam como ordinais


def _base_type(dtype: str) -> str:
    return dtype.split("(")[0].upper()


def infer_measurement(dtype: str, n_distinct: int | None) -> str:
    base = _base_type(dtype)
    if base in _INT_TYPES and n_distinct is not None and n_distinct <= ORDINAL_MAX_LEVELS:
        return "ordinal"
    if base in _NUM_TYPES or base == "DECIMAL":
        return "scale"
    return "nominal"  # VARCHAR, BOOLEAN, DATE, ... (datas: refinamento futuro)


def parquet_path(dataset_id: str) -> Path:
    return settings.data_dir / "datasets" / f"{dataset_id}.parquet"


_db = db.connect


def _row_to_dataset(row: sqlite3.Row) -> Dataset:
    return Dataset(
        id=row["id"], name=row["name"], table_name=row["table_name"], n_rows=row["n_rows"],
        columns=[Column(**c) for c in json.loads(row["columns_json"])], created_at=row["created_at"],
    )


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", Path(name).stem.lower()).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"d_{slug}" if slug else "dataset"
    return slug[:48]


def _unique_table_name(con: sqlite3.Connection, base: str) -> str:
    taken = {r["table_name"] for r in con.execute("SELECT table_name FROM datasets")}
    name, i = base, 1
    while name in taken:
        i += 1
        name = f"{base}_{i}"
    return name


def list_datasets() -> list[Dataset]:
    with closing(_db()) as con:
        return [_row_to_dataset(r) for r in con.execute("SELECT * FROM datasets ORDER BY created_at DESC")]


def get_dataset(dataset_id: str) -> Dataset:
    with closing(_db()) as con:
        row = con.execute("SELECT * FROM datasets WHERE id = ?", [dataset_id]).fetchone()
    if row is None:
        raise DatasetNotFound(f"dataset not found: {dataset_id}")
    return _row_to_dataset(row)


def delete_dataset(dataset_id: str) -> None:
    get_dataset(dataset_id)
    with closing(_db()) as con, con:
        con.execute("DELETE FROM datasets WHERE id = ?", [dataset_id])
    parquet_path(dataset_id).unlink(missing_ok=True)


def update_measurements(dataset_id: str, measurement: dict[str, str]) -> Dataset:
    ds = get_dataset(dataset_id)
    names = {c.name for c in ds.columns}
    unknown = sorted(set(measurement) - names)
    if unknown:
        raise DatasetError(f"unknown column(s): {', '.join(unknown)}")
    for c in ds.columns:
        if c.name in measurement:
            c.measurement = measurement[c.name]
    with closing(_db()) as con, con:
        con.execute("UPDATE datasets SET columns_json = ? WHERE id = ?", [json.dumps([c.model_dump() for c in ds.columns]), dataset_id])
    return ds


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def describe_parquet(path: Path) -> tuple[int, list[Column]]:
    """Nº de linhas e colunas (tipo, nível de medida inferido, nº de distintos) de um Parquet já gravado."""
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"SET memory_limit={sql_str(settings.query_memory_limit)}")
        src = f"read_parquet({sql_str(str(path))})"
        described = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()  # (name, type, ...)
        n_rows = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]
        columns = []
        for col_name, dtype, *_ in described:
            n_distinct = None
            if _base_type(dtype) not in _FLOAT_TYPES:  # decide ordinal vs. escalar e quais colunas servem de grupo (2 níveis)
                q = '"' + col_name.replace('"', '""') + '"'
                n_distinct = con.execute(f"SELECT count(DISTINCT {q}) FROM {src}").fetchone()[0]
            columns.append(Column(name=col_name, dtype=dtype, measurement=infer_measurement(dtype, n_distinct), n_distinct=n_distinct))
        return n_rows, columns
    finally:
        con.close()


def register(dataset_id: str, name: str, n_rows: int, columns: list[Column]) -> Dataset:
    """Grava o dataset no registro (o Parquet já existe em parquet_path(dataset_id))."""
    with closing(_db()) as db, db:
        table_name = _unique_table_name(db, slugify(name))
        db.execute(
            "INSERT INTO datasets (id, name, table_name, n_rows, columns_json, created_at) VALUES (?,?,?,?,?,?)",
            [dataset_id, name, table_name, n_rows, json.dumps([c.model_dump() for c in columns]), datetime.now(timezone.utc).isoformat()],
        )
    return get_dataset(dataset_id)


def ingest_csv(src: Path, name: str) -> Dataset:
    """Lê um CSV (tipos inferidos pelo DuckDB sobre o arquivo todo), grava Parquet e registra."""
    dataset_id = uuid.uuid4().hex
    out = parquet_path(dataset_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"SET memory_limit={sql_str(settings.query_memory_limit)}")
        try:
            con.execute(f"CREATE TABLE raw AS SELECT * FROM read_csv({sql_str(str(src))}, sample_size=-1)")
        except duckdb.Error as exc:
            raise DatasetError(f"could not parse CSV: {str(exc).splitlines()[0]}") from exc
        if not con.execute("DESCRIBE raw").fetchall() or con.execute("SELECT count(*) FROM raw").fetchone()[0] == 0:
            raise DatasetError("CSV has no data rows")
        con.execute(f"COPY raw TO {sql_str(str(out))} (FORMAT parquet, COMPRESSION zstd)")
        n_rows, columns = describe_parquet(out)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    finally:
        con.close()
    return register(dataset_id, name, n_rows, columns)
