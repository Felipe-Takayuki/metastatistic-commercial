import httpx
import pytest

from app import auth, avatars
from app.config import settings
from app.main import app
from app.storage import S3StorageProvider, reset_storage_provider

from test_auth import login, make_user, new_client, setup_admin

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32


@pytest.fixture(autouse=True)
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)


@pytest.fixture(autouse=True)
def fresh_storage():
    reset_storage_provider()  # o provedor é singleton e guarda o data_dir do primeiro teste
    yield
    reset_storage_provider()


def put(c, data: bytes, name="foto.png", ctype="image/png"):
    return c.put("/auth/me/avatar", files={"file": (name, data, ctype)})


async def test_upload_get_and_replace(tmp_path):
    async with new_client() as c:
        await setup_admin(c)
        assert (await c.get("/auth/me")).json()["avatar_version"] is None
        assert (await c.get("/auth/me/avatar")).status_code == 404

        r = await put(c, PNG)
        assert r.status_code == 200, r.text
        first = r.json()["avatar_version"]
        assert first
        got = await c.get("/auth/me/avatar")
        assert got.status_code == 200 and got.content == PNG
        assert got.headers["content-type"] == "image/png"
        assert got.headers["x-content-type-options"] == "nosniff"
        assert "avatar_key" not in (await c.get("/auth/me")).json()  # a chave do objeto não sai da API

        stored = list((settings.data_dir / "tenants" / avatars.STORAGE_NAMESPACE).rglob("*.png"))
        assert len(stored) == 1

        r = await put(c, JPEG, "outra.jpg", "image/jpeg")
        assert r.status_code == 200
        assert r.json()["avatar_version"] != first
        assert (await c.get("/auth/me/avatar")).headers["content-type"] == "image/jpeg"
        files = [p for p in (settings.data_dir / "tenants" / avatars.STORAGE_NAMESPACE).rglob("*") if p.is_file()]
        assert [p.suffix for p in files] == [".jpg"]  # a foto anterior foi apagada


@pytest.mark.parametrize("data,ctype", [(WEBP, "image/webp"), (GIF, "image/gif")])
async def test_other_accepted_formats(data, ctype):
    async with new_client() as c:
        await setup_admin(c)
        assert (await put(c, data, "x", ctype)).status_code == 200
        assert (await c.get("/auth/me/avatar")).headers["content-type"] == ctype


async def test_type_comes_from_bytes_not_from_the_client():
    async with new_client() as c:
        await setup_admin(c)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        assert (await put(c, svg, "x.png", "image/png")).status_code == 422
        assert (await put(c, b"not an image at all", "x.png", "image/png")).status_code == 422
        assert (await put(c, b"", "x.png", "image/png")).status_code == 422
        # PNG de verdade enviado com tipo e nome mentirosos é aceito e servido como PNG
        assert (await put(c, PNG, "x.txt", "text/plain")).status_code == 200
        assert (await c.get("/auth/me/avatar")).headers["content-type"] == "image/png"


async def test_size_limit():
    async with new_client() as c:
        await setup_admin(c)
        assert (await put(c, PNG + b"\x00" * avatars.MAX_BYTES)).status_code == 413
        assert (await put(c, PNG + b"\x00" * (avatars.MAX_BYTES - len(PNG)))).status_code == 200  # exatamente no limite
        assert (await c.get("/auth/me")).json()["avatar_version"]


async def test_delete_avatar():
    async with new_client() as c:
        await setup_admin(c)
        await put(c, PNG)
        assert (await c.delete("/auth/me/avatar")).status_code == 204
        assert (await c.get("/auth/me")).json()["avatar_version"] is None
        assert (await c.get("/auth/me/avatar")).status_code == 404
        assert not [p for p in (settings.data_dir / "tenants").rglob("*") if p.is_file()]
        assert (await c.delete("/auth/me/avatar")).status_code == 204  # idempotente


async def test_each_user_has_their_own_avatar():
    async with new_client() as admin:
        await setup_admin(admin)
        await make_user(admin, "bia", "viewer")
        await put(admin, PNG)
        bia = await login("bia")
        assert (await bia.get("/auth/me/avatar")).status_code == 404  # não enxerga a foto da admin
        await put(bia, JPEG, "b.jpg", "image/jpeg")
        assert (await admin.get("/auth/me/avatar")).content == PNG
        assert (await bia.get("/auth/me/avatar")).content == JPEG
        listed = {u["username"]: u["avatar_version"] for u in (await admin.get("/users")).json()}
        assert listed["ana"] and listed["bia"] and listed["ana"] != listed["bia"]
        await bia.aclose()


async def test_requires_session():
    async with new_client() as anon:
        assert (await put(anon, PNG)).status_code == 401
        assert (await anon.get("/auth/me/avatar")).status_code == 401
        assert (await anon.delete("/auth/me/avatar")).status_code == 401


async def test_auth_disabled_has_no_profile(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    async with new_client() as c:
        assert (await put(c, PNG)).status_code == 409
        assert (await c.get("/auth/me/avatar")).status_code == 409


async def test_avatar_survives_a_new_session():
    async with new_client() as c:
        await setup_admin(c, password="senha-forte-1")
        await put(c, PNG)
    async with new_client() as again:
        assert (await again.post("/auth/login", json={"username": "ana", "password": "senha-forte-1"})).status_code == 200
        assert (await again.get("/auth/me/avatar")).content == PNG


# ---------- armazenamento de objetos (S3/Garage) ----------

class FakeS3:
    """Cliente boto3 mínimo em memória."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.down = False

    def put_object(self, Bucket, Key, Body):
        if self.down:
            raise ConnectionError("garage is down")
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if self.down:
            raise ConnectionError("garage is down")
        if (Bucket, Key) not in self.objects:
            err = Exception("NoSuchKey")
            err.response = {"Error": {"Code": "NoSuchKey"}}
            raise err
        import io
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise Exception("404")

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def garage(monkeypatch, tmp_path):
    fake = FakeS3()
    provider = S3StorageProvider(bucket="metastatistic", base_cache_dir=tmp_path)
    provider._client = fake
    import app.storage as storage
    monkeypatch.setattr(storage, "_provider_instance", provider)
    return fake


async def test_avatar_is_stored_in_the_bucket(garage):
    async with new_client() as c:
        me = await setup_admin(c)
        await put(c, PNG)
        keys = [k for (b, k) in garage.objects if b == "metastatistic"]
        assert len(keys) == 1 and keys[0].startswith(f"tenants/{avatars.STORAGE_NAMESPACE}/avatars/{me['id']}/") and keys[0].endswith(".png")
        assert (await c.get("/auth/me/avatar")).content == PNG

        await put(c, JPEG, "b.jpg", "image/jpeg")
        keys = [k for (_, k) in garage.objects]
        assert len(keys) == 1 and keys[0].endswith(".jpg")  # a anterior saiu do bucket

        await c.delete("/auth/me/avatar")
        assert garage.objects == {}


async def test_storage_down_is_503_and_keeps_the_current_avatar(garage):
    async with new_client() as c:
        await setup_admin(c)
        await put(c, PNG)
        garage.down = True
        assert (await put(c, JPEG, "b.jpg", "image/jpeg")).status_code == 503
        assert (await c.get("/auth/me/avatar")).status_code == 503  # falha de rede não vira "sem foto"
        garage.down = False
        assert (await c.get("/auth/me/avatar")).content == PNG  # a troca que falhou não mexeu na foto atual


async def test_object_missing_from_bucket_reads_as_no_avatar(garage):
    async with new_client() as c:
        await setup_admin(c)
        await put(c, PNG)
        garage.objects.clear()
        assert (await c.get("/auth/me/avatar")).status_code == 404
