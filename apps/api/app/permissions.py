"""Quem LÊ o quê: acesso por dataset (restrito a uma lista) e segurança por linha (atributos do usuário).

- **Acesso**: dataset `restricted` só é lido pelo dono, por administradores e pelos usuários da lista (`grants`).
  Sem configuração = aberto a todos que entraram. Dataset ilegível não aparece na lista, dá 404 e some do SQL
  (a tabela simplesmente não existe para quem não pode lê-la).
- **Linhas**: com uma regra `coluna ↔ atributo`, o usuário só vê as linhas cuja coluna (como texto) está entre os
  valores do atributo dele (lista separada por vírgulas). Atributo ausente => nenhuma linha (falha fechada). Administradores
  e o dono do dataset veem tudo. O SQL enxerga a visão filtrada; as análises recebem um Parquet filtrado.
- **Derivados**: dataset salvo a partir de uma consulta herda a restrição das fontes. Fonte com acesso restrito => o
  derivado fica restrito, com a interseção das listas; fonte com regra de linha => restrito só ao dono/administradores
  (abrir depois é uma decisão explícita).
"""
import hashlib
import re
from contextlib import closing
from pathlib import Path

import duckdb

from . import access, auth, db, datasets
from .config import settings
from .schemas import Dataset

ATTR_NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


class AccessConfigError(ValueError):
    """Pedido inválido de configuração de acesso -> HTTP 422."""


# ---------- atributos dos usuários ----------

def get_attributes(user_id: str) -> dict[str, str]:
    with closing(db.connect()) as con:
        return {r["name"]: r["value"] for r in con.execute("SELECT name, value FROM user_attributes WHERE user_id = ?", [user_id])}


def set_attributes(user_id: str, attributes: dict[str, str]) -> None:
    clean: dict[str, str] = {}
    for name, value in attributes.items():
        name = name.strip().lower()
        if not ATTR_NAME.match(name):
            raise AccessConfigError(f"invalid attribute name {name!r}: use letters, digits and _ (start with a letter, up to 31)")
        value = ",".join(v.strip() for v in str(value).split(",") if v.strip())
        if len(value) > 500:
            raise AccessConfigError(f"attribute {name!r} is too long")
        if value:
            clean[name] = value
    with closing(db.connect()) as con, con:
        con.execute("DELETE FROM user_attributes WHERE user_id = ?", [user_id])
        con.executemany("INSERT INTO user_attributes VALUES (?,?,?)", [(user_id, k, v) for k, v in clean.items()])


def attribute_values(user: auth.User, attribute: str) -> list[str]:
    raw = get_attributes(user.id).get(attribute, "")
    return [v for v in raw.split(",") if v]


# ---------- acesso por dataset ----------

def _grants(con, dataset_id: str) -> set[str]:
    return {r["user_id"] for r in con.execute("SELECT user_id FROM dataset_grants WHERE dataset_id = ?", [dataset_id])}


def is_restricted(dataset_id: str) -> bool:
    with closing(db.connect()) as con:
        row = con.execute("SELECT restricted FROM dataset_acl WHERE dataset_id = ?", [dataset_id]).fetchone()
    return bool(row and row["restricted"])


def can_read(user: auth.User, dataset_id: str) -> bool:
    if user.can("admin"):
        return True
    with closing(db.connect()) as con:
        row = con.execute("SELECT restricted FROM dataset_acl WHERE dataset_id = ?", [dataset_id]).fetchone()
        if not row or not row["restricted"]:
            return True
        return access.owner_id("dataset", dataset_id) == user.id or user.id in _grants(con, dataset_id)


def readable(user: auth.User, items: list[Dataset]) -> list[Dataset]:
    return [d for d in items if can_read(user, d.id)]


def get_config(dataset_id: str) -> dict:
    with closing(db.connect()) as con:
        acl = con.execute("SELECT restricted FROM dataset_acl WHERE dataset_id = ?", [dataset_id]).fetchone()
        rls = con.execute("SELECT column_name, attribute FROM dataset_rls WHERE dataset_id = ?", [dataset_id]).fetchone()
        grants = sorted(_grants(con, dataset_id))
    return {"restricted": bool(acl and acl["restricted"]), "user_ids": grants,
            "rls": {"column": rls["column_name"], "attribute": rls["attribute"]} if rls else None}


def set_config(dataset_id: str, restricted: bool, user_ids: list[str], rls: dict | None) -> dict:
    ds = datasets.get_dataset(dataset_id)  # 404 se não existe
    with closing(db.connect()) as con:
        known = {r["id"] for r in con.execute("SELECT id FROM users")}
    unknown = sorted(set(user_ids) - known)
    if unknown:
        raise AccessConfigError(f"unknown user id(s): {', '.join(unknown)}")
    if rls is not None:
        if rls["column"] not in {c.name for c in ds.columns}:
            raise AccessConfigError(f"unknown column: {rls['column']}")
        if not ATTR_NAME.match(rls["attribute"]):
            raise AccessConfigError("invalid attribute name: use lowercase letters, digits and _ (start with a letter)")
    with closing(db.connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO dataset_acl VALUES (?,?)", [dataset_id, int(restricted)])
        con.execute("DELETE FROM dataset_grants WHERE dataset_id = ?", [dataset_id])
        con.executemany("INSERT INTO dataset_grants VALUES (?,?)", [(dataset_id, u) for u in sorted(set(user_ids))])
        if rls is None:
            con.execute("DELETE FROM dataset_rls WHERE dataset_id = ?", [dataset_id])
        else:
            con.execute("INSERT OR REPLACE INTO dataset_rls VALUES (?,?,?)", [dataset_id, rls["column"], rls["attribute"]])
    _drop_filtered_views(dataset_id)  # a regra mudou: os Parquets filtrados antigos não valem mais
    return get_config(dataset_id)


def apply_default_visibility(dataset_id: str) -> None:
    """Com DATASETS_PRIVATE_BY_DEFAULT, o dataset novo só é lido pelo dono e por administradores até ser compartilhado."""
    if not settings.datasets_private_by_default or is_restricted(dataset_id):
        return
    cfg = get_config(dataset_id)
    set_config(dataset_id, True, cfg["user_ids"], cfg["rls"])


def forget_dataset(dataset_id: str) -> None:
    _drop_filtered_views(dataset_id)
    with closing(db.connect()) as con, con:
        for table in ("dataset_acl", "dataset_grants", "dataset_rls"):
            con.execute(f"DELETE FROM {table} WHERE dataset_id = ?", [dataset_id])


def decorate(items: list[Dataset], user: auth.User) -> list[Dataset]:
    """Preenche `restricted` e `row_filtered` (a regra de linhas se aplica a ESTE usuário)."""
    if not items:
        return items
    with closing(db.connect()) as con:
        restricted = {r["dataset_id"] for r in con.execute("SELECT dataset_id FROM dataset_acl WHERE restricted = 1")}
        rls = {r["dataset_id"] for r in con.execute("SELECT dataset_id FROM dataset_rls")}
    return [d.model_copy(update={"restricted": d.id in restricted, "row_filtered": d.id in rls and not _bypasses(user, d.id)}) for d in items]


# ---------- segurança por linha ----------

def _bypasses(user: auth.User, dataset_id: str) -> bool:
    return user.can("admin") or access.owner_id("dataset", dataset_id) == user.id


def row_filter(user: auth.User, dataset_id: str) -> tuple[str, list[str]] | None:
    """(coluna, valores permitidos) quando a regra se aplica a este usuário; None = vê tudo."""
    with closing(db.connect()) as con:
        rule = con.execute("SELECT column_name, attribute FROM dataset_rls WHERE dataset_id = ?", [dataset_id]).fetchone()
    if rule is None or _bypasses(user, dataset_id):
        return None
    return rule["column_name"], attribute_values(user, rule["attribute"])


def where_clause(column: str, values: list[str]) -> str:
    if not values:
        return "FALSE"  # sem o atributo: nenhuma linha
    quoted = '"' + column.replace('"', '""') + '"'
    return f"CAST({quoted} AS VARCHAR) IN ({', '.join(datasets.sql_str(v) for v in values)})"


def visible_views(user: auth.User) -> list[tuple[Dataset, Path]]:
    """Datasets que o usuário lê, cada um com o Parquet que o sandbox do SQL pode abrir: o original ou, havendo regra
    de linhas, a cópia já filtrada. O Parquet completo NÃO fica acessível ao sandbox desse usuário (defesa em
    profundidade: mesmo uma falha do analisador de SQL não alcança as linhas proibidas)."""
    return [(ds, datasets.parquet_path(analysis_source(user, ds))) for ds in readable(user, datasets.list_datasets())]


def analysis_source(user: auth.User, ds: Dataset) -> str:
    """Id de Parquet que o motor R deve ler: o próprio dataset, ou uma cópia filtrada (criada sob demanda)."""
    rule = row_filter(user, ds.id)
    if rule is None:
        return ds.id
    column, values = rule
    view_id = hashlib.sha256(f"{ds.id}|{column}|{'|'.join(sorted(values))}".encode()).hexdigest()[:32]
    out = datasets.parquet_path(view_id)
    if not out.exists():
        tmp = out.with_suffix(".tmp")
        con = duckdb.connect(":memory:")
        try:
            con.execute(f"SET memory_limit={datasets.sql_str(settings.query_memory_limit)}")
            src = datasets.sql_str(str(datasets.parquet_path(ds.id)))
            con.execute(f"COPY (SELECT * FROM read_parquet({src}) WHERE {where_clause(column, values)}) "
                        f"TO {datasets.sql_str(str(tmp))} (FORMAT parquet, COMPRESSION zstd)")
        finally:
            con.close()
        tmp.replace(out)
        with closing(db.connect()) as c, c:
            c.execute("INSERT OR REPLACE INTO rls_views VALUES (?,?)", [view_id, ds.id])
    return view_id


def _drop_filtered_views(dataset_id: str) -> None:
    with closing(db.connect()) as con, con:
        ids = [r["view_id"] for r in con.execute("SELECT view_id FROM rls_views WHERE dataset_id = ?", [dataset_id])]
        con.execute("DELETE FROM rls_views WHERE dataset_id = ?", [dataset_id])
    for vid in ids:
        datasets.parquet_path(vid).unlink(missing_ok=True)


def present(items: list[Dataset], user: auth.User) -> list[Dataset]:
    """O que o usuário lê, já com dono, `can_edit` e as marcas de acesso/linhas (resposta padrão dos datasets)."""
    return decorate(access.annotate("dataset", readable(user, items), user), user)


# ---------- derivados ----------

def inherit_for_derived(new_id: str, source_ids: list[str]) -> None:
    """O dataset salvo de uma consulta herda a restrição das fontes (ver o cabeçalho do módulo)."""
    if not source_ids:
        return
    with closing(db.connect()) as con:
        restricted = [i for i in source_ids if (r := con.execute("SELECT restricted FROM dataset_acl WHERE dataset_id = ?", [i]).fetchone()) and r["restricted"]]
        has_rls = any(con.execute("SELECT 1 FROM dataset_rls WHERE dataset_id = ?", [i]).fetchone() for i in source_ids)
        grants: set[str] | None = None
        for i in restricted:
            grants = _grants(con, i) if grants is None else grants & _grants(con, i)
    if not restricted and not has_rls:
        return
    with closing(db.connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO dataset_acl VALUES (?,1)", [new_id])
        con.executemany("INSERT INTO dataset_grants VALUES (?,?)", [(new_id, u) for u in sorted(set() if has_rls else (grants or set()))])
