import httpx
import pytest

from app import auth
from app.config import settings
from app.main import app

from conftest import SALES_CSV


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def setup_admin(c, username="ana", password="senha-forte-1"):
    r = await c.post("/auth/setup", json={"username": username, "password": password, "display_name": "Ana"})
    assert r.status_code == 201, r.text
    return r.json()


async def make_user(admin, username, role, password="senha-forte-2"):
    r = await admin.post("/users", json={"username": username, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


async def login(username, password="senha-forte-2") -> httpx.AsyncClient:
    c = new_client()
    r = await c.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


# ---------- desligada: nada muda ----------

async def test_auth_disabled_everything_open(client):
    s = (await client.get("/auth/status")).json()
    assert s == {"auth_enabled": False, "needs_setup": False, "user": auth.ANONYMOUS_ADMIN.public()}
    assert (await client.get("/datasets")).status_code == 200
    assert (await client.post("/auth/login", json={"username": "x", "password": "y"})).status_code == 409
    assert (await client.get("/users")).status_code == 200  # "admin" anônimo


# ---------- primeiro acesso e login ----------

async def test_everything_requires_session(client, auth_on):
    for method, url in [("get", "/datasets"), ("get", "/reports"), ("get", "/dashboards"), ("post", "/queries/run"),
                        ("post", "/analyses/run"), ("get", "/analyses/status"), ("get", "/users"), ("get", "/auth/me")]:
        assert (await getattr(client, method)(url)).status_code == 401, url
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/auth/status")).json()["needs_setup"] is True


async def test_setup_creates_admin_once_and_logs_in(client, auth_on):
    user = await setup_admin(client)
    assert user["role"] == "admin" and "password" not in str(user)
    assert (await client.get("/auth/me")).json()["username"] == "ana"  # o cookie da sessão já vale
    s = (await client.get("/auth/status")).json()
    assert s["needs_setup"] is False and s["user"]["username"] == "ana"
    again = await new_client().post("/auth/setup", json={"username": "eve", "password": "senha-forte-9"})
    assert again.status_code == 409  # ninguém "assume" um sistema já configurado


async def test_register_creates_admin_first_then_editor(client, auth_on):
    # Primeiro cadastro: vira admin
    r1 = await client.post("/auth/register", json={"username": "carlos", "password": "senha-forte-1", "display_name": "Carlos"})
    assert r1.status_code == 201, r1.text
    u1 = r1.json()
    assert u1["role"] == "admin"
    assert u1["username"] == "carlos"
    assert (await client.get("/auth/me")).json()["username"] == "carlos"

    # Segundo cadastro: vira editor
    c2 = new_client()
    r2 = await c2.post("/auth/register", json={"username": "mariana", "password": "senha-forte-2", "display_name": "Mariana"})
    assert r2.status_code == 201, r2.text
    u2 = r2.json()
    assert u2["role"] == "editor"
    assert u2["username"] == "mariana"
    assert (await c2.get("/auth/me")).json()["username"] == "mariana"

    # Conflito de username: 409
    c3 = new_client()
    r3 = await c3.post("/auth/register", json={"username": "carlos", "password": "senha-forte-3"})
    assert r3.status_code == 409
    assert "já existe" in r3.json()["detail"].lower()


async def test_register_disabled_auth_fails(client):
    r = await client.post("/auth/register", json={"username": "novo", "password": "senha-forte-1"})
    assert r.status_code == 409


async def test_setup_validates_username_and_password(client, auth_on):
    assert (await client.post("/auth/setup", json={"username": "ab", "password": "senha-forte-1"})).status_code == 422
    assert (await client.post("/auth/setup", json={"username": "ana", "password": "curta"})).status_code == 422
    assert (await client.post("/auth/setup", json={"username": "a na", "password": "senha-forte-1"})).status_code == 422
    assert (await client.get("/auth/status")).json()["needs_setup"] is True


async def test_login_logout_and_wrong_password(client, auth_on):
    await setup_admin(client)
    anon = new_client()
    bad = await anon.post("/auth/login", json={"username": "ana", "password": "errada-errada"})
    assert bad.status_code == 401
    unknown = await anon.post("/auth/login", json={"username": "ninguem", "password": "errada-errada"})
    assert unknown.status_code == 401 and unknown.json() == bad.json()  # não revela se o usuário existe
    ok = await anon.post("/auth/login", json={"username": "ANA", "password": "senha-forte-1"})  # nome sem diferenciar caixa
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert (await anon.get("/datasets")).status_code == 200
    assert (await anon.post("/auth/logout")).status_code == 204
    assert (await anon.get("/datasets")).status_code == 401


async def test_login_locks_after_repeated_failures(client, auth_on, monkeypatch):
    await setup_admin(client)
    monkeypatch.setattr(settings, "login_max_failures", 3)
    anon = new_client()
    for _ in range(3):
        assert (await anon.post("/auth/login", json={"username": "ana", "password": "x" * 9})).status_code == 401
    locked = await anon.post("/auth/login", json={"username": "ana", "password": "senha-forte-1"})
    assert locked.status_code == 429  # nem a senha certa entra durante o bloqueio
    monkeypatch.setattr(settings, "login_lock_s", 0.0)
    assert (await anon.post("/auth/login", json={"username": "ana", "password": "senha-forte-1"})).status_code == 200


async def test_session_token_is_not_stored_in_clear(client, auth_on):
    await setup_admin(client)
    token = client.cookies.get("ms_session")
    import sqlite3
    rows = sqlite3.connect(settings.data_dir / "meta.db").execute("SELECT token_hash FROM sessions").fetchall()
    assert rows and token not in rows[0][0] and len(rows[0][0]) == 64


async def test_expired_session_is_rejected(client, auth_on, monkeypatch):
    await setup_admin(client)
    monkeypatch.setattr(settings, "session_ttl_hours", -1)
    c = new_client()
    await c.post("/auth/login", json={"username": "ana", "password": "senha-forte-1"})
    assert (await c.get("/datasets")).status_code == 401


# ---------- papéis ----------

async def test_roles_viewer_editor_admin(client, auth_on):
    await setup_admin(client)
    await make_user(client, "vera", "viewer")
    await make_user(client, "edu", "editor")
    viewer, editor = await login("vera"), await login("edu")

    # viewer: lê e roda consulta; não altera nada
    assert (await viewer.get("/datasets")).status_code == 200
    assert (await viewer.get("/reports")).status_code == 200
    up = await viewer.post("/datasets", files={"file": ("v.csv", SALES_CSV.encode(), "text/csv")})
    assert up.status_code == 403
    assert (await viewer.post("/reports", json={"title": "x", "blocks": []})).status_code == 403
    assert (await viewer.post("/dashboards", json={"title": "x", "tiles": []})).status_code == 403
    assert (await viewer.get("/users")).status_code == 403

    # editor: cria e apaga conteúdo; não gerencia usuários
    up = await editor.post("/datasets", files={"file": ("v.csv", SALES_CSV.encode(), "text/csv")})
    assert up.status_code == 201
    ds = up.json()["id"]
    q = await viewer.post("/queries/run", json={"sql": f'SELECT COUNT(*) AS n FROM "{up.json()["table_name"]}"'})
    assert q.status_code == 200 and q.json()["rows"] == [[4]]
    rep = await editor.post("/reports", json={"title": "R", "blocks": []})
    assert rep.status_code == 201
    assert (await viewer.get(f"/reports/{rep.json()['id']}")).status_code == 200
    assert (await viewer.delete(f"/reports/{rep.json()['id']}")).status_code == 403
    assert (await editor.delete(f"/reports/{rep.json()['id']}")).status_code == 204
    assert (await editor.post("/users", json={"username": "zed", "password": "senha-forte-3"})).status_code == 403
    assert (await viewer.delete(f"/datasets/{ds}")).status_code == 403
    assert (await editor.delete(f"/datasets/{ds}")).status_code == 204


# ---------- gestão de usuários ----------

async def test_admin_manages_users(client, auth_on):
    await setup_admin(client)
    u = await make_user(client, "bia", "viewer")
    dup = await client.post("/users", json={"username": "BIA", "password": "senha-forte-2"})
    assert dup.status_code == 409
    assert (await client.post("/users", json={"username": "cid", "password": "senha-forte-2", "role": "root"})).status_code == 422
    assert {x["username"] for x in (await client.get("/users")).json()} == {"ana", "bia"}

    bia = await login("bia")
    patched = await client.patch(f"/users/{u['id']}", json={"role": "editor", "display_name": "Bia S."})
    assert patched.json()["role"] == "editor" and patched.json()["display_name"] == "Bia S."
    assert (await bia.post("/reports", json={"title": "x", "blocks": []})).status_code == 201  # papel vale na hora

    await client.patch(f"/users/{u['id']}", json={"active": False})
    assert (await bia.get("/datasets")).status_code == 401  # desativar derruba a sessão
    assert (await new_client().post("/auth/login", json={"username": "bia", "password": "senha-forte-2"})).status_code == 401

    assert (await client.delete(f"/users/{u['id']}")).status_code == 204
    assert (await client.delete(f"/users/{u['id']}")).status_code == 404


async def test_password_reset_by_admin_revokes_sessions(client, auth_on):
    await setup_admin(client)
    u = await make_user(client, "bia", "viewer")
    bia = await login("bia")
    await client.patch(f"/users/{u['id']}", json={"password": "outra-senha-9"})
    assert (await bia.get("/datasets")).status_code == 401
    assert (await new_client().post("/auth/login", json={"username": "bia", "password": "senha-forte-2"})).status_code == 401
    await login("bia", "outra-senha-9")


async def test_cannot_remove_last_admin(client, auth_on):
    me = await setup_admin(client)
    assert (await client.patch(f"/users/{me['id']}", json={"role": "editor"})).status_code == 422
    assert (await client.patch(f"/users/{me['id']}", json={"active": False})).status_code == 422
    assert (await client.delete(f"/users/{me['id']}")).status_code == 422
    other = await make_user(client, "ben", "admin")
    assert (await client.patch(f"/users/{me['id']}", json={"role": "viewer"})).status_code == 200  # agora há outro admin
    ben = await login("ben")
    assert (await ben.delete(f"/users/{other['id']}")).status_code == 422  # ele é o último


async def test_change_own_password(client, auth_on):
    await setup_admin(client)
    wrong = await client.post("/auth/password", json={"current": "nao-e-essa", "new": "nova-senha-9"})
    assert wrong.status_code == 401
    short = await client.post("/auth/password", json={"current": "senha-forte-1", "new": "curta"})
    assert short.status_code == 422
    other_session = await login("ana", "senha-forte-1")
    assert (await client.post("/auth/password", json={"current": "senha-forte-1", "new": "nova-senha-9"})).status_code == 204
    assert (await client.get("/auth/me")).status_code == 200      # a sessão atual continua
    assert (await other_session.get("/auth/me")).status_code == 401  # as outras caem
    await login("ana", "nova-senha-9")
    assert (await new_client().post("/auth/login", json={"username": "ana", "password": "senha-forte-1"})).status_code == 401


def test_password_hash_is_salted_and_verifiable():
    a, b = auth.hash_password("segredo-longo"), auth.hash_password("segredo-longo")
    assert a != b and auth.verify_password("segredo-longo", a) and not auth.verify_password("outro", a)
    assert not auth.verify_password("x", "lixo")
