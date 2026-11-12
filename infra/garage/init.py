#!/usr/bin/env python3
"""Prepara o Garage de nó único para o Metastatistic: layout, bucket e chave de acesso. Idempotente.

Roda como serviço de uma execução só (`garage-init` no docker-compose) e usa a API de administração v1 do Garage
(v0.9 a v1.x). Só biblioteca padrão. Sai com código != 0 se algo falhar, o que impede a `api` de subir sem bucket.

Variáveis: GARAGE_ADMIN_URL, GARAGE_ADMIN_TOKEN, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, GARAGE_CAPACITY_BYTES.
O ID da chave precisa ter o formato do Garage: "GK" + 24 hex; o segredo, 64 hex.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ADMIN_URL = os.environ.get("GARAGE_ADMIN_URL", "http://garage:3903").rstrip("/")
TOKEN = os.environ.get("GARAGE_ADMIN_TOKEN", "")
BUCKET = os.environ.get("S3_BUCKET", "metastatistic")
KEY_ID = os.environ.get("S3_ACCESS_KEY", "")
SECRET = os.environ.get("S3_SECRET_KEY", "")
CAPACITY = int(os.environ.get("GARAGE_CAPACITY_BYTES", str(10 * 1024**3)))
KEY_NAME = "metastatistic-api"
WAIT_S = int(os.environ.get("GARAGE_INIT_WAIT_S", "90"))


class AdminError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def call(method: str, path: str, body=None, query: dict | None = None):
    url = f"{ADMIN_URL}/v1{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise AdminError(exc.code, exc.read().decode(errors="replace")[:300]) from exc


def _is_not_found(exc: "AdminError") -> bool:
    return exc.status == 404 or (exc.status == 400 and "not found" in str(exc).lower())


def retry(what: str, fn, seconds: float = WAIT_S):
    """O Garage leva alguns segundos para aceitar chamadas depois de subir e depois de aplicar o layout."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return fn()
        except (AdminError, urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            if isinstance(exc, AdminError) and exc.status in (401, 403):
                raise  # token errado não melhora esperando
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{what}: {exc}") from exc
            time.sleep(1)


def ensure_layout(node_id: str) -> None:
    layout = call("GET", "/layout")
    if any(role["id"] == node_id for role in layout["roles"]):
        print("layout: nó já tem papel, nada a fazer")
        return
    call("POST", "/layout", [{"id": node_id, "zone": "dc1", "capacity": CAPACITY, "tags": []}])
    call("POST", "/layout/apply", {"version": layout["version"] + 1})
    print(f"layout: nó {node_id[:8]} aplicado ({CAPACITY} bytes)")


def ensure_bucket() -> str:
    try:
        return call("GET", "/bucket", query={"globalAlias": BUCKET})["id"]
    except AdminError as exc:
        if not _is_not_found(exc):
            raise
    bucket_id = call("POST", "/bucket", {"globalAlias": BUCKET})["id"]
    print(f"bucket: '{BUCKET}' criado")
    return bucket_id


def ensure_key() -> None:
    try:
        info = call("GET", "/key", query={"id": KEY_ID, "showSecretKey": "true"})
    except AdminError as exc:
        # chave inexistente: o Garage 1.0 responde 400 "Access key not found" (versões antigas, 404)
        if not _is_not_found(exc):
            raise
        call("POST", "/key/import", {"name": KEY_NAME, "accessKeyId": KEY_ID, "secretAccessKey": SECRET})
        print(f"chave: {KEY_ID} importada")
        return
    if info.get("secretAccessKey") not in (None, SECRET):
        raise RuntimeError(
            f"a chave {KEY_ID} já existe no Garage com OUTRO segredo. Use o segredo original ou remova a chave "
            f"(`docker compose exec garage /garage key delete --yes {KEY_ID}`) e rode de novo."
        )
    print("chave: já existe")


def main() -> int:
    problems = []
    if not TOKEN:
        problems.append("GARAGE_ADMIN_TOKEN vazio")
    if not re.fullmatch(r"GK[0-9a-f]{24}", KEY_ID):
        problems.append("S3_ACCESS_KEY deve ser 'GK' + 24 caracteres hex (gere: echo GK$(openssl rand -hex 12))")
    if not re.fullmatch(r"[0-9a-f]{64}", SECRET):
        problems.append("S3_SECRET_KEY deve ter 64 caracteres hex (gere: openssl rand -hex 32)")
    if problems:
        print("configuração inválida:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2

    node_id = retry("aguardando o Garage", lambda: call("GET", "/status"))["node"]
    ensure_layout(node_id)
    bucket_id = retry("criando o bucket", ensure_bucket)
    ensure_key()
    call("POST", "/bucket/allow", {
        "bucketId": bucket_id, "accessKeyId": KEY_ID,
        "permissions": {"read": True, "write": True, "owner": False},
    })
    print(f"pronto: bucket '{BUCKET}' acessível pela chave {KEY_ID}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"garage-init falhou: {exc}", file=sys.stderr)
        sys.exit(1)
