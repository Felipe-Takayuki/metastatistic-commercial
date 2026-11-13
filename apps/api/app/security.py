"""Dependências do FastAPI: quem está chamando e o que ele pode fazer."""
from fastapi import Depends, HTTPException, Request

import dataclasses

from . import access, audit, auth, tenancy
from .config import settings

COOKIE = "ms_session"


# Teto de papel na plataforma que cada papel de organização permite: a mesma pessoa pode ser editora numa organização e só
# leitora em outra. O administrador da plataforma não é limitado; `admin` da plataforma não se herda de nenhuma organização.
ORG_ROLE_CAP = {"owner": "editor", "admin": "editor", "statistician": "editor", "analyst": "editor", "viewer": "viewer"}


def effective_role(platform_role: str, org_role: str | None) -> str:
    cap = ORG_ROLE_CAP.get(org_role or "")
    if platform_role == "admin" or cap is None:
        return platform_role
    return cap if auth.ROLES.index(cap) < auth.ROLES.index(platform_role) else platform_role


def current_user(request: Request) -> auth.User:
    if not settings.auth_enabled:
        return auth.ANONYMOUS_ADMIN
    user = auth.user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "authentication required")
    role = effective_role(user.role, tenancy.org_role())
    return dataclasses.replace(user, role=role) if role != user.role else user


def _require(role: str):
    def dep(request: Request, user: auth.User = Depends(current_user)) -> auth.User:
        if not user.can(role):
            audit.log(user, "denied", detail=f"{request.method} {request.url.path} (exige {role})")
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
            audit.log(user, "denied", kind, request.path_params[param], request.method)
            raise HTTPException(403, "only the owner or an administrator can change this item")
        return user

    return dep
