from fastapi import APIRouter, Depends, HTTPException

from .. import access, auth
from ..schemas import CollectionIn
from ..security import current_user, require_editor, require_viewer

router = APIRouter(prefix="/collections", tags=["collections"], dependencies=[Depends(require_viewer)])


def _owned(cid: str, user: auth.User = Depends(require_editor)) -> auth.User:
    try:
        owner = access.collection_owner(cid)
    except access.CollectionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    if not access.may_modify(user, owner):
        raise HTTPException(403, "only the owner or an administrator can change this collection")
    return user


@router.get("")
def list_collections(user: auth.User = Depends(current_user)) -> list[dict]:
    return access.list_collections(user)


@router.post("", status_code=201)
def create_collection(body: CollectionIn, user: auth.User = Depends(require_editor)) -> dict:
    created = access.create_collection(body.name, user)
    return next(c for c in access.list_collections(user) if c["id"] == created["id"])


@router.patch("/{cid}", dependencies=[Depends(_owned)])
def rename_collection(cid: str, body: CollectionIn, user: auth.User = Depends(current_user)) -> dict:
    access.rename_collection(cid, body.name)
    return next(c for c in access.list_collections(user) if c["id"] == cid)


@router.delete("/{cid}", status_code=204, dependencies=[Depends(_owned)])
def delete_collection(cid: str) -> None:
    access.delete_collection(cid)
