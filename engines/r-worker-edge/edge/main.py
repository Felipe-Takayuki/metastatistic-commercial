"""Borda do worker R remoto: autenticação por token, sincronização de datasets e proxy de /run e /health.

Para tirar o worker R (pesado) do servidor principal: o `api`/`stat-orchestrator` falam com ESTE serviço, que roda na mesma
máquina do worker. Como lá não existe o volume de datasets compartilhado, o cliente envia o Parquet antes da análise
(`PUT /datasets/{id}`); o worker R continua lendo `DATA_DIR/datasets/<id>.parquet` exatamente como antes (o código R não muda).

Endpoints (todos exigem `Authorization: Bearer <token>`, exceto /live):
    GET    /live                 liveness (sem token, para healthcheck do container)
    GET    /health               repassa ao worker R
    POST   /run                  repassa ao worker R (o corpo é o mesmo que o cliente mandaria ao worker)
    GET    /datasets/{id}        200 {"size": n} se o Parquet já está aqui, senão 404
    PUT    /datasets/{id}        grava o Parquet (corpo bruto); recusa o que não parece Parquet ou passa do limite
    DELETE /datasets/{id}
Os datasets são imutáveis (um id nunca muda de conteúdo), então um Parquet já presente nunca precisa ser regravado.
O cache é limitado: ao passar de MAX_CACHE_MB removem-se os menos usados (o cliente reenvia se um dataset sumir).
"""
import hmac
import json
import os
import re
import tempfile
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response

ID_RE = re.compile(r"^[0-9a-f]{32}$")  # o mesmo formato que o worker R aceita (e que impede path traversal)
MIN_TOKEN_LENGTH = 32
PARQUET_MAGIC = b"PAR1"


def _json(status: int, body: dict) -> Response:
    return Response(json.dumps(body), status_code=status, media_type="application/json")


def create_app(*, token: str, data_dir: Path, worker_url: str, max_cache_bytes: int = 2 * 1024**3,
               max_upload_bytes: int = 1024**3, client: httpx.AsyncClient | None = None) -> FastAPI:
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(f"R_WORKER_TOKEN deve ter pelo menos {MIN_TOKEN_LENGTH} caracteres (gere: openssl rand -hex 32)")
    datasets = Path(data_dir) / "datasets"
    datasets.mkdir(parents=True, exist_ok=True)
    upstream = client or httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0))
    worker = worker_url.rstrip("/")

    def authenticated(request: Request) -> None:
        sent = request.headers.get("authorization", "")
        if not (sent.startswith("Bearer ") and hmac.compare_digest(sent[7:].encode(), token.encode())):
            raise HTTPException(401, "invalid or missing token", headers={"WWW-Authenticate": "Bearer"})

    app = FastAPI(title="Metastatistic R worker edge", docs_url=None, redoc_url=None, openapi_url=None)

    def path_of(dataset_id: str) -> Path:
        if not ID_RE.match(dataset_id):
            raise HTTPException(400, "invalid dataset id")
        return datasets / f"{dataset_id}.parquet"

    def evict(keep: Path) -> None:
        files = sorted((p for p in datasets.glob("*.parquet") if p != keep), key=lambda p: p.stat().st_mtime)  # menos usado primeiro
        total = sum(p.stat().st_size for p in files) + (keep.stat().st_size if keep.exists() else 0)
        for p in files:
            if total <= max_cache_bytes:
                break
            total -= p.stat().st_size
            p.unlink(missing_ok=True)

    @app.get("/live")
    def live() -> dict:
        return {"status": "ok"}

    @app.get("/health", dependencies=[Depends(authenticated)])
    async def health() -> Response:
        try:
            resp = await upstream.get(f"{worker}/health", timeout=5.0)
        except httpx.HTTPError as exc:
            return _json(503, {"status": "unreachable", "message": type(exc).__name__})
        return Response(resp.content, status_code=resp.status_code, media_type="application/json")

    @app.get("/datasets/{dataset_id}", dependencies=[Depends(authenticated)])
    def dataset_info(dataset_id: str) -> dict:
        path = path_of(dataset_id)
        if not path.is_file():
            raise HTTPException(404, "dataset not found")
        return {"size": path.stat().st_size}

    @app.put("/datasets/{dataset_id}", dependencies=[Depends(authenticated)], status_code=201)
    async def put_dataset(dataset_id: str, request: Request) -> dict:
        target = path_of(dataset_id)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_upload_bytes:
            raise HTTPException(413, "dataset too large")
        fd, tmp_name = tempfile.mkstemp(dir=datasets, suffix=".part")
        tmp = Path(tmp_name)
        size = 0
        try:
            with os.fdopen(fd, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(413, "dataset too large")
                    out.write(chunk)
            with tmp.open("rb") as f:   # um Parquet começa e termina com "PAR1"
                head = f.read(4)
                f.seek(max(size - 4, 0))
                tail = f.read(4)
            if size < 12 or head != PARQUET_MAGIC or tail != PARQUET_MAGIC:
                raise HTTPException(422, "not a parquet file")
            os.replace(tmp, target)   # atômico: o worker R nunca lê um arquivo pela metade
        finally:
            tmp.unlink(missing_ok=True)
        evict(keep=target)
        return {"size": size}

    @app.delete("/datasets/{dataset_id}", dependencies=[Depends(authenticated)], status_code=204)
    def delete_dataset(dataset_id: str) -> None:
        path_of(dataset_id).unlink(missing_ok=True)

    @app.post("/run", dependencies=[Depends(authenticated)])
    async def run(request: Request) -> Response:
        body = await request.body()
        timeout = 90.0
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                timeout = float(payload.get("timeout_s") or 60.0) + 30.0   # folga para o worker recriar o motor
                dataset_id = payload.get("dataset_id")
                if isinstance(dataset_id, str) and ID_RE.match(dataset_id):
                    used = datasets / f"{dataset_id}.parquet"
                    if used.exists():
                        used.touch()   # marca uso recente (a remoção do cache é pelo menos usado)
        except (ValueError, TypeError):
            pass   # corpo inválido: o worker responde com o erro de sempre
        try:
            resp = await upstream.post(f"{worker}/run", content=body, headers={"content-type": "application/json"}, timeout=timeout)
        except httpx.ConnectError as exc:
            return _json(503, {"code": "worker_unavailable", "message": f"worker R inacessível: {exc}"})
        except httpx.TimeoutException:
            return _json(504, {"code": "timeout", "message": "o worker R não respondeu a tempo"})
        return Response(resp.content, status_code=resp.status_code, media_type="application/json")

    return app


def app_from_env() -> FastAPI:
    return create_app(
        token=os.environ.get("R_WORKER_TOKEN", ""),
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        worker_url=os.environ.get("R_WORKER_URL", "http://r-worker:8000"),
        max_cache_bytes=int(float(os.environ.get("MAX_CACHE_MB", "2048")) * 1024 * 1024),
        max_upload_bytes=int(float(os.environ.get("MAX_UPLOAD_MB", "1024")) * 1024 * 1024),
    )
