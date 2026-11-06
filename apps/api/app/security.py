"""Dependências do FastAPI: quem está chamando e o que ele pode fazer."""
from fastapi import Depends, HTTPException, Request

from . import auth
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
