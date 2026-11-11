"""Foto de perfil: validação da imagem e gravação no armazenamento de objetos (Garage/S3 ou disco).

O tipo da imagem vem dos bytes (assinatura do arquivo), nunca do `Content-Type` nem do nome enviados pelo cliente. SVG fica
de fora de propósito: ele pode carregar script. Cada envio grava um objeto novo (`avatars/<usuário>/<id>.<ext>`) e apaga o
anterior, então o id do objeto serve de versão para o cache do navegador.
"""
import uuid

from . import auth
from .config import settings
from .storage import get_storage_provider

# Os objetos ficam num "tenant" reservado: a foto é do usuário, não de uma organização.
STORAGE_NAMESPACE = "_profiles"
MAX_BYTES = 2 * 1024 * 1024

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


class AvatarError(ValueError):
    """Erro do pedido -> HTTP 4xx."""


class AvatarTooLarge(AvatarError):
    pass


class StorageUnavailable(RuntimeError):
    """O armazenamento de objetos não respondeu -> HTTP 503."""


def sniff_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate(data: bytes) -> str:
    """Devolve o tipo da imagem ou levanta AvatarError."""
    if not data:
        raise AvatarError("empty file")
    if len(data) > MAX_BYTES:
        raise AvatarTooLarge(f"image exceeds {MAX_BYTES // (1024 * 1024)} MB")
    content_type = sniff_type(data)
    if content_type is None:
        raise AvatarError("unsupported image format (use PNG, JPEG, WebP or GIF)")
    return content_type


def _storage():
    return get_storage_provider()


def save(user: auth.User, data: bytes) -> str:
    """Grava a foto nova, aponta o usuário para ela e apaga a anterior. Devolve o tipo da imagem."""
    content_type = validate(data)
    key = f"avatars/{user.id}/{uuid.uuid4().hex}.{_EXT[content_type]}"
    try:
        _storage().upload(STORAGE_NAMESPACE, key, data)
    except Exception as exc:
        raise StorageUnavailable(f"could not store the image: {exc}") from exc
    previous = user.avatar_key
    auth.set_avatar(user.id, key, content_type)
    if previous:
        _discard(previous)
    return content_type


def load(user: auth.User) -> tuple[bytes, str] | None:
    """(bytes, tipo) da foto atual, ou None se o usuário não tem foto."""
    if not user.avatar_key:
        return None
    try:
        return _storage().download(STORAGE_NAMESPACE, user.avatar_key), user.avatar_type or "application/octet-stream"
    except FileNotFoundError:
        return None  # o objeto sumiu do bucket: tratamos como "sem foto"
    except Exception as exc:
        raise StorageUnavailable(f"could not read the image: {exc}") from exc


def remove(user: auth.User) -> None:
    if user.avatar_key:
        auth.set_avatar(user.id, None, None)
        _discard(user.avatar_key)


def _discard(key: str) -> None:
    """Apaga o objeto; se o armazenamento falhar, sobra um objeto órfão, mas o usuário não fica sem resposta."""
    try:
        _storage().delete(STORAGE_NAMESPACE, key)
    except Exception:
        pass
