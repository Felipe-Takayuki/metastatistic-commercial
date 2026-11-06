"""Dono e coleção dos recursos (datasets, relatórios, dashboards) e a regra de quem pode alterá-los.

Regra: `viewer` só lê; `editor` altera/exclui o que **criou** (e o que não tem dono: criado antes dos usuários ou com a
autenticação desligada); `admin` altera tudo. Coleções são pastas planas, compartilhadas por relatórios e dashboards.
O dono fica numa tabela à parte (`resources`): recurso sem linha ali = legado, sem dono, na raiz.
"""
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel

from . import auth, db

KINDS = ("dataset", "report", "dashboard")


class AccessError(ValueError):
    pass


class CollectionNotFound(AccessError):
    pass


def _owner_of(user: auth.User) -> str | None:
    return None if user.id == auth.ANONYMOUS_ADMIN.id else user.id


def claim(kind: str, rid: str, user: auth.User) -> None:
    """Registra o criador de um recurso novo."""
    assert kind in KINDS
    with closing(db.connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO resources (kind, id, owner_id, collection_id) VALUES (?,?,?,NULL)", [kind, rid, _owner_of(user)])


def forget(kind: str, rid: str) -> None:
    with closing(db.connect()) as con, con:
        con.execute("DELETE FROM resources WHERE kind = ? AND id = ?", [kind, rid])


def owner_id(kind: str, rid: str) -> str | None:
    with closing(db.connect()) as con:
        row = con.execute("SELECT owner_id FROM resources WHERE kind = ? AND id = ?", [kind, rid]).fetchone()
    return row["owner_id"] if row else None


def may_modify(user: auth.User, owner: str | None) -> bool:
    if not user.can("editor"):
        return False
    return user.can("admin") or owner is None or owner == user.id


def can_modify(user: auth.User, kind: str, rid: str) -> bool:
    return may_modify(user, owner_id(kind, rid))


def set_collection(kind: str, rid: str, collection_id: str | None) -> None:
    if collection_id is not None:
        get_collection(collection_id)  # 404 se não existe
    with closing(db.connect()) as con, con:
        con.execute(
            "INSERT INTO resources (kind, id, owner_id, collection_id) VALUES (?,?,NULL,?) "
            "ON CONFLICT(kind, id) DO UPDATE SET collection_id = excluded.collection_id",
            [kind, rid, collection_id],
        )


def annotate(kind: str, items: Iterable[Any], user: auth.User) -> list[Any]:
    """Preenche `owner_name`, `collection_id` e `can_edit` em modelos pydantic ou dicts (uma consulta só)."""
    items = list(items)
    if not items:
        return items
    ids = [i["id"] if isinstance(i, dict) else i.id for i in items]
    with closing(db.connect()) as con:
        marks = ",".join("?" * len(ids))
        meta = {r["id"]: r for r in con.execute(
            f"SELECT r.id, r.owner_id, r.collection_id, u.display_name AS owner_name FROM resources r "
            f"LEFT JOIN users u ON u.id = r.owner_id WHERE r.kind = ? AND r.id IN ({marks})", [kind, *ids])}
    out = []
    for item, rid in zip(items, ids):
        m = meta.get(rid)
        extra = {"owner_name": m["owner_name"] if m else None, "collection_id": m["collection_id"] if m else None,
                 "can_edit": may_modify(user, m["owner_id"] if m else None)}
        out.append({**item, **extra} if isinstance(item, dict) else item.model_copy(update=extra))
    return out


def annotate_one(kind: str, item: BaseModel, user: auth.User) -> BaseModel:
    return annotate(kind, [item], user)[0]


# ---------- coleções ----------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_collection(name: str, user: auth.User) -> dict:
    cid = uuid.uuid4().hex
    with closing(db.connect()) as con, con:
        con.execute("INSERT INTO collections VALUES (?,?,?,?)", [cid, name, _owner_of(user), _now()])
    return get_collection(cid)


def get_collection(cid: str) -> dict:
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM collections WHERE id = ?", [cid]).fetchone()
    if row is None:
        raise CollectionNotFound(f"collection not found: {cid}")
    return dict(row)


def list_collections(user: auth.User) -> list[dict]:
    with closing(db.connect()) as con:
        rows = con.execute(
            "SELECT c.id, c.name, c.owner_id, u.display_name AS owner_name, "
            " (SELECT COUNT(*) FROM resources r WHERE r.collection_id = c.id AND r.kind = 'report') AS n_reports, "
            " (SELECT COUNT(*) FROM resources r WHERE r.collection_id = c.id AND r.kind = 'dashboard') AS n_dashboards "
            "FROM collections c LEFT JOIN users u ON u.id = c.owner_id ORDER BY lower(c.name)").fetchall()
    return [{"id": r["id"], "name": r["name"], "owner_name": r["owner_name"], "n_reports": r["n_reports"],
             "n_dashboards": r["n_dashboards"], "can_edit": may_modify(user, r["owner_id"])} for r in rows]


def rename_collection(cid: str, name: str) -> dict:
    get_collection(cid)
    with closing(db.connect()) as con, con:
        con.execute("UPDATE collections SET name = ? WHERE id = ?", [name, cid])
    return get_collection(cid)


def delete_collection(cid: str) -> None:
    """Os itens da coleção voltam para a raiz (nada é excluído junto)."""
    get_collection(cid)
    with closing(db.connect()) as con, con:
        con.execute("UPDATE resources SET collection_id = NULL WHERE collection_id = ?", [cid])
        con.execute("DELETE FROM collections WHERE id = ?", [cid])


def collection_owner(cid: str) -> str | None:
    return get_collection(cid)["owner_id"]
