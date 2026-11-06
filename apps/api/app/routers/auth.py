from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import audit, auth, permissions
from ..config import settings
from ..security import COOKIE, current_user, require_admin, require_editor

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
    attributes: dict[str, str] | None = Field(default=None, description="atributos para a segurança por linha (substitui todos)")


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
    audit.log(user, "setup", "user", user.id, "administrador criado")
    return user.public()


@router.post("/login")
def login(body: Credentials, response: Response) -> dict:
    if not settings.auth_enabled:
        raise HTTPException(409, "authentication is disabled")
    try:
        user = auth.authenticate(body.username, body.password)
    except auth.AuthError as exc:
        audit.log(None, "login_locked" if isinstance(exc, auth.LoginLocked) else "login_failed", "user", None, username=body.username.strip().lower()[:60])
        raise _http(exc) from exc
    _start_session(response, user)
    audit.log(user, "login", "user", user.id)
    return user.public()


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    audit.log(auth.user_for_token(request.cookies.get(COOKIE)), "logout")
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
    audit.log(user, "change_password", "user", user.id)


@router.get("/directory")
def directory(_: auth.User = Depends(require_editor)) -> list[dict]:
    """Usuários ativos (id, usuário, nome) para escolher quem pode ler um dataset. Sem papéis nem atributos."""
    return [{"id": u.id, "username": u.username, "display_name": u.display_name} for u in auth.list_users() if u.active]


@users_router.get("")
def list_users() -> list[dict]:
    return [{**u.public(), "attributes": permissions.get_attributes(u.id)} for u in auth.list_users()]


@users_router.post("", status_code=201)
def create_user(body: UserIn, admin: auth.User = Depends(current_user)) -> dict:
    try:
        created = auth.create_user(body.username, body.password, body.display_name, body.role)
    except auth.AuthError as exc:
        raise _http(exc) from exc
    audit.log(admin, "create_user", "user", created.id, f"{created.username} ({created.role})")
    return {**created.public(), "attributes": {}}


@users_router.patch("/{user_id}")
def patch_user(user_id: str, body: UserPatch, admin: auth.User = Depends(current_user)) -> dict:
    try:
        before = auth.get_user(user_id)
        updated = auth.update_user(user_id, display_name=body.display_name, role=body.role, active=body.active, password=body.password)
        if body.attributes is not None:
            permissions.set_attributes(user_id, body.attributes)
    except auth.AuthError as exc:
        raise _http(exc) from exc
    except permissions.AccessConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    changes = [n for n, on in [("papel", body.role is not None and body.role != before.role), ("situação", body.active is not None and body.active != before.active),
                               ("senha", body.password is not None), ("atributos", body.attributes is not None), ("nome", body.display_name is not None)] if on]
    audit.log(admin, "update_user", "user", user_id, f"{updated.username}: {', '.join(changes) or 'sem mudanças'}"
              + (f" → {updated.role}" if body.role is not None and body.role != before.role else ""))
    return {**updated.public(), "attributes": permissions.get_attributes(user_id)}


@users_router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, admin: auth.User = Depends(current_user)) -> None:
    try:
        name = auth.get_user(user_id).username
        auth.delete_user(user_id)
        audit.log(admin, "delete_user", "user", user_id, name)
    except auth.AuthError as exc:
        raise _http(exc) from exc


audit_router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@audit_router.get("")
def list_audit(limit: int = 100, before_id: int | None = None, action: str | None = None) -> list[dict]:
    """Eventos mais recentes primeiro. Paginação: passe o menor `id` recebido em `before_id`."""
    return audit.list_events(limit, before_id, action)
