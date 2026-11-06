import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict
from app.models import TokenPayload


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))


class JWTError(Exception):
    pass


class TokenExpiredError(JWTError):
    pass


class InvalidTokenError(JWTError):
    pass


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    tier: str,
    secret_key: str,
    expires_in_minutes: int = 1440,
    email: str | None = None,
) -> str:
    now = int(time.time())
    exp = now + (expires_in_minutes * 60)
    
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "tier": tier,
        "exp": exp,
        "iat": now,
    }
    if email:
        payload["email"] = email

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str, secret_key: str) -> TokenPayload:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Invalid token format: expected 3 parts")

    header_b64, payload_b64, sig_b64 = parts

    # Verifica assinatura
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception as e:
        raise InvalidTokenError(f"Malformed signature encoding: {e}")

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise InvalidTokenError("Invalid token signature")

    # Decodifica payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload_dict = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise InvalidTokenError(f"Malformed payload: {e}")

    # Checa expiração
    exp = payload_dict.get("exp")
    if not exp or not isinstance(exp, (int, float)):
        raise InvalidTokenError("Token missing or invalid 'exp' claim")

    now = int(time.time())
    if now > exp:
        raise TokenExpiredError("Token has expired")

    try:
        return TokenPayload(**payload_dict)
    except Exception as e:
        raise InvalidTokenError(f"Invalid claims in token payload: {e}")
