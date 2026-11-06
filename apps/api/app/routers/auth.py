from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth
from ..config import settings
from ..security import COOKIE, current_user, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


class Credentials(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class SetupIn(Credentials):
    display_name: str | None = Field(default=None, max_length=120)


class UserIn(SetupIn):
    role: str = "viewer"


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


def _http(exc: auth.AuthError) -> HTTPException:
    code = {auth.InvalidCredentials: 401, auth.LoginLocked: 429, auth.UserNotFound: 404, auth.UserConflict: 409}.get(type(exc), 422)
    return HTTPException(code, str(exc))


def _start_session(response: Response, user: auth.User) -> None:
    token, expires = auth.create_session(user)
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600, expires=expires, path="/",
    )


@router.get("/status")
def status(request: Request) -> dict:
    """Público: a interface decide entre tela de login, de primeiro acesso ou o app."""
    user = auth.user_for_token(request.cookies.get(COOKIE)) if settings.auth_enabled else auth.ANONYMOUS_ADMIN
    return {
        "auth_enabled": settings.auth_enabled,
        "needs_setup": settings.auth_enabled and auth.user_count() == 0,
        "user": user.public() if user else None,
    }


@router.post("/setup", status_code=201)
def setup(body: SetupIn, response: Response) -> dict:
    """Primeiro acesso: cria o administrador. Só funciona enquanto não existe nenhum usuário."""
    if not settings.auth_enabled:
        raise HTTPException(409, "authentication is disabled")
    if auth.user_count() > 0:
        raise HTTPException(409, "setup already done")
    try:
        user = auth.create_user(body.username, body.password, body.display_name, role="admin")
    except auth.AuthError as exc:
        raise _http(exc) from exc
    _start_session(response, user)
    return user.public()


@router.post("/login")
def login(body: Credentials, response: Response) -> dict:
    if not settings.auth_enabled:
        raise HTTPException(409, "authentication is disabled")
    try:
        user = auth.authenticate(body.username, body.password)
    except auth.AuthError as exc:
        raise _http(exc) from exc
    _start_session(response, user)
    return user.public()


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    auth.end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(user: auth.User = Depends(current_user)) -> dict:
    return user.public()


@router.post("/password", status_code=204)
def change_password(body: dict, response: Response, user: auth.User = Depends(current_user)) -> None:
    """O próprio usuário troca a senha (exige a atual). Derruba as outras sessões e abre uma nova."""
    if user.id == auth.ANONYMOUS_ADMIN.id:
        raise HTTPException(409, "authentication is disabled")
    try:
        auth.authenticate(user.username, str(body.get("current", "")))
        auth.update_user(user.id, password=str(body.get("new", "")))
    except auth.AuthError as exc:
        raise _http(exc) from exc
    _start_session(response, user)


@users_router.get("")
def list_users() -> list[dict]:
    return [u.public() for u in auth.list_users()]


@users_router.post("", status_code=201)
def create_user(body: UserIn) -> dict:
    try:
        return auth.create_user(body.username, body.password, body.display_name, body.role).public()
    except auth.AuthError as exc:
        raise _http(exc) from exc


@users_router.patch("/{user_id}")
def patch_user(user_id: str, body: UserPatch) -> dict:
    try:
        return auth.update_user(user_id, display_name=body.display_name, role=body.role, active=body.active, password=body.password).public()
    except auth.AuthError as exc:
        raise _http(exc) from exc


@users_router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str) -> None:
    try:
        auth.delete_user(user_id)
    except auth.AuthError as exc:
        raise _http(exc) from exc
