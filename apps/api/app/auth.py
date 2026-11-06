"""Usuários, papéis e sessões.

Papéis (cada um inclui o anterior): `viewer` lê e roda consultas/análises; `editor` cria e altera conteúdo
(datasets, relatórios, dashboards); `admin` gerencia usuários. Senhas: scrypt da biblioteca padrão com sal por
usuário. Sessão: token aleatório entregue em cookie HttpOnly; o banco guarda só o SHA-256 dele, então um vazamento
do `meta.db` não entrega sessões válidas.
"""
import base64
import hashlib
import hmac
import secrets
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings

ROLES = ("viewer", "editor", "admin")
MIN_PASSWORD = 8
_SCRYPT = dict(n=2**14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


class AuthError(ValueError):
    """Erro do pedido -> HTTP 4xx (a classe base é 422)."""


class InvalidCredentials(AuthError):
    pass


class LoginLocked(AuthError):
    pass


class UserNotFound(AuthError):
    pass


class UserConflict(AuthError):
    pass


@dataclass(frozen=True)
class User:
    id: str
    username: str
    display_name: str
    role: str
    active: bool = True

    def can(self, role: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(role)

    def public(self) -> dict:
        return {"id": self.id, "username": self.username, "display_name": self.display_name, "role": self.role, "active": self.active}


# Quando a autenticação está desligada todo mundo é este usuário (comportamento anterior à fase de usuários).
ANONYMOUS_ADMIN = User(id="anonymous", username="anonymous", display_name="Sem autenticação", role="admin")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- senhas ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


# Hash de uma senha qualquer: login com usuário inexistente gasta o mesmo tempo (não revela quem existe).
_DUMMY_HASH = hash_password("não-é-a-senha-de-ninguém")


def _check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"password must have at least {MIN_PASSWORD} characters")
    if len(password) > 200:
        raise AuthError("password is too long")


def _normalize_username(username: str) -> str:
    name = username.strip().lower()
    if not (3 <= len(name) <= 60) or any(ch.isspace() for ch in name):
        raise AuthError("username must have 3–60 characters, without spaces")
    return name


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise AuthError(f"role must be one of {', '.join(ROLES)}")


# ---------- usuários ----------

def _row_user(row) -> User:
    return User(id=row["id"], username=row["username"], display_name=row["display_name"], role=row["role"], active=bool(row["active"]))


def user_count() -> int:
    with closing(db.connect()) as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def create_user(username: str, password: str, display_name: str | None = None, role: str = "viewer") -> User:
    name = _normalize_username(username)
    _check_role(role)
    _check_password_rules(password)
    user_id = uuid.uuid4().hex
    try:
        with closing(db.connect()) as con, con:
            con.execute(
                "INSERT INTO users (id, username, display_name, password_hash, role, active, created_at) VALUES (?,?,?,?,?,1,?)",
                [user_id, name, (display_name or name).strip()[:120] or name, hash_password(password), role, _now().isoformat()],
            )
    except Exception as exc:  # sqlite3.IntegrityError (nome repetido)
        if "UNIQUE" in str(exc):
            raise UserConflict(f"username already exists: {name}") from exc
        raise
    return get_user(user_id)


def get_user(user_id: str) -> User:
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", [user_id]).fetchone()
    if row is None:
        raise UserNotFound(f"user not found: {user_id}")
    return _row_user(row)


def list_users() -> list[User]:
    with closing(db.connect()) as con:
        return [_row_user(r) for r in con.execute("SELECT * FROM users ORDER BY username")]


def _active_admins(con, excluding: str | None = None) -> int:
    return con.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?", [excluding or ""]).fetchone()[0]


def update_user(user_id: str, *, display_name: str | None = None, role: str | None = None,
                active: bool | None = None, password: str | None = None) -> User:
    current = get_user(user_id)
    new_role = current.role if role is None else role
    new_active = current.active if active is None else active
    _check_role(new_role)
    if password is not None:
        _check_password_rules(password)
    with closing(db.connect()) as con, con:
        # nunca deixar o sistema sem um administrador ativo (ninguém mais conseguiria gerenciar usuários)
        if (new_role != "admin" or not new_active) and _active_admins(con, excluding=user_id) == 0 and current.role == "admin" and current.active:
            raise AuthError("cannot remove the last active administrator")
        con.execute(
            "UPDATE users SET display_name = ?, role = ?, active = ? WHERE id = ?",
            [(display_name if display_name is not None else current.display_name).strip()[:120] or current.username, new_role, int(new_active), user_id],
        )
        if password is not None:
            con.execute("UPDATE users SET password_hash = ? WHERE id = ?", [hash_password(password), user_id])
        if password is not None or not new_active:
            con.execute("DELETE FROM sessions WHERE user_id = ?", [user_id])  # trocar a senha/desativar derruba as sessões
    return get_user(user_id)


def delete_user(user_id: str) -> None:
    current = get_user(user_id)
    with closing(db.connect()) as con, con:
        if current.role == "admin" and current.active and _active_admins(con, excluding=user_id) == 0:
            raise AuthError("cannot remove the last active administrator")
        # o que a pessoa criou passa a "sem dono" (qualquer editor mantém), em vez de ficar só com administradores
        con.execute("DELETE FROM user_attributes WHERE user_id = ?", [user_id])
        con.execute("DELETE FROM dataset_grants WHERE user_id = ?", [user_id])
        con.execute("UPDATE resources SET owner_id = NULL WHERE owner_id = ?", [user_id])
        con.execute("UPDATE collections SET owner_id = NULL WHERE owner_id = ?", [user_id])
        con.execute("DELETE FROM users WHERE id = ?", [user_id])


# ---------- login e sessões ----------

_failures: dict[str, tuple[int, float]] = {}  # usuário -> (falhas seguidas, quando foi a última)


def _check_lock(username: str) -> None:
    count, last = _failures.get(username, (0, 0.0))
    if count >= settings.login_max_failures:
        wait = settings.login_lock_s - (time.monotonic() - last)
        if wait > 0:
            raise LoginLocked(f"too many failed attempts; try again in {int(wait) + 1} s")
        _failures.pop(username, None)


def reset_login_state() -> None:
    _failures.clear()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(username: str, password: str) -> User:
    name = username.strip().lower()
    _check_lock(name)
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", [name]).fetchone()
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if row is None or not ok or not row["active"]:
        count, _ = _failures.get(name, (0, 0.0))
        _failures[name] = (count + 1, time.monotonic())
        raise InvalidCredentials("invalid username or password")
    _failures.pop(name, None)
    return _row_user(row)


def create_session(user: User) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(hours=settings.session_ttl_hours)
    with closing(db.connect()) as con, con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", [_now().isoformat()])  # faxina oportunista
        con.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen) VALUES (?,?,?,?,?)",
                    [_hash_token(token), user.id, _now().isoformat(), expires.isoformat(), _now().isoformat()])
    return token, expires


def user_for_token(token: str | None) -> User | None:
    if not token:
        return None
    with closing(db.connect()) as con:
        row = con.execute(
            "SELECT u.*, s.expires_at, s.last_seen FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            [_hash_token(token)],
        ).fetchone()
        if row is None or not row["active"] or row["expires_at"] < _now().isoformat():
            return None
        now = _now()
        last = datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None
        if settings.session_idle_hours > 0 and last and now - last > timedelta(hours=settings.session_idle_hours):
            with con:
                con.execute("DELETE FROM sessions WHERE token_hash = ?", [_hash_token(token)])  # parada por tempo demais: cai
            return None
        if last is None or now - last > timedelta(seconds=60):  # renova a "última atividade" no máximo 1x por minuto
            with con:
                con.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", [now.isoformat(), _hash_token(token)])
    return _row_user(row)


def end_session(token: str | None) -> None:
    if token:
        with closing(db.connect()) as con, con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", [_hash_token(token)])
