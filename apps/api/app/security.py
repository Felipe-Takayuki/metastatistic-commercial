"""Dependências do FastAPI: quem está chamando e o que ele pode fazer."""
from fastapi import Depends, HTTPException, Request

from . import access, auth
from .config import settings

COOKIE = "ms_session"


def current_user(request: Request) -> auth.User:
    if not settings.auth_enabled:
        return auth.ANONYMOUS_ADMIN
    user = auth.user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "authentication required")
    return user


def _require(role: str):
    def dep(user: auth.User = Depends(current_user)) -> auth.User:
        if not user.can(role):
            raise HTTPException(403, f"requires role {role}")
        return user

    return dep


require_viewer = _require("viewer")
require_editor = _require("editor")
require_admin = _require("admin")


def can_modify(kind: str, param: str):
    """Dependência: o usuário é editor E dono do recurso (ou admin, ou o recurso não tem dono)."""
    def dep(request: Request, user: auth.User = Depends(require_editor)) -> auth.User:
        if not access.can_modify(user, kind, request.path_params[param]):
            raise HTTPException(403, "only the owner or an administrator can change this item")
        return user

    return dep
