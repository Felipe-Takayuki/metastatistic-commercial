"""Execução de análises: cache de resultados + deduplicação de pedidos idênticos + pool de workers."""
import asyncio
import hashlib
import json
from collections import OrderedDict
from typing import Any

import httpx

from .config import settings
from .pool import ConnectFailure, PoolError, WorkerPool, WorkerReply, WorkerTimeout
from .remote_datasets import RemoteDatasets, RemoteSyncError, is_dataset_missing


class AnalysisFailed(PoolError):
    """Falha de uma análise específica (pedido inválido ou erro do motor), já com status HTTP e mensagem."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def cache_key(analysis: str, dataset_id: str, options: dict[str, Any], columns: list[str], measurement: dict[str, str]) -> str:
    """Identifica um resultado: mesma análise, dataset, opções, colunas lidas e níveis de medida => mesmo resultado."""
    raw = json.dumps(
        {"a": analysis, "d": dataset_id, "o": options, "c": columns, "m": measurement},
        sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class ResultCache:
    """LRU limitado por nº de entradas E por bytes (os resultados trazem gráficos em base64)."""

    def __init__(self, max_entries: int, max_bytes: int):
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._items: OrderedDict[str, tuple[int, dict[str, Any]]] = OrderedDict()
        self._bytes = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            self.misses += 1
            return None
        self._items.move_to_end(key)
        self.hits += 1
        return item[1]

    def put(self, key: str, body: dict[str, Any]) -> None:
        size = len(json.dumps(body, separators=(",", ":")))
        if size > self._max_bytes:  # um resultado maior que o cache inteiro não entra (e não expulsa os outros)
            return
        if key in self._items:
            self._bytes -= self._items.pop(key)[0]
        self._items[key] = (size, body)
        self._bytes += size
        while len(self._items) > self._max_entries or self._bytes > self._max_bytes:
            _, (old_size, _) = self._items.popitem(last=False)
            self._bytes -= old_size

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._items), "bytes": self._bytes, "hits": self.hits, "misses": self.misses}


class AnalysisService:
    def __init__(self, pool: WorkerPool, cache: ResultCache, *, timeout_s: float):
        self.pool, self.cache, self.timeout_s = pool, cache, timeout_s
        self._inflight: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._waiting: dict[str, int] = {}

    def status(self) -> dict[str, Any]:
        return {**self.pool.status(), "inflight": len(self._inflight), "cache": self.cache.stats(), "timeout_s": self.timeout_s}

    async def run(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        if (hit := self.cache.get(key)) is not None:
            return hit
        task = self._inflight.get(key)
        if task is None:  # primeiro a pedir: executa; os idênticos que chegarem enquanto isso esperam este mesmo resultado
            task = asyncio.ensure_future(self._execute(key, payload))
            self._inflight[key] = task
            task.add_done_callback(lambda t, k=key: (self._inflight.pop(k, None), t.cancelled() or t.exception()))
        self._waiting[key] = self._waiting.get(key, 0) + 1
        try:
            return await asyncio.shield(task)
        finally:
            self._waiting[key] -= 1
            if self._waiting[key] <= 0:
                self._waiting.pop(key, None)
                if not task.done():  # todos desistiram: não vale ocupar a fila/worker para ninguém
                    task.cancel()

    async def _execute(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        reply = await self.pool.run({**payload, "timeout_s": self.timeout_s})
        body = self._interpret(reply)
        if body.get("status") == "complete":  # só resultados completos entram no cache (erros/timeouts não)
            self.cache.put(key, body)
        return body

    def _interpret(self, reply: WorkerReply) -> dict[str, Any]:
        s, body = reply.status, reply.body if isinstance(reply.body, dict) else {}
        msg = str(body.get("message", ""))[:500]
        if s == 200:
            return body
        if s == 504 or body.get("code") == "timeout":
            raise WorkerTimeout(f"A análise excedeu o limite de {self.timeout_s:g} s e foi interrompida.")
        if 400 <= s < 500:
            raise AnalysisFailed(422, msg or "Pedido de análise inválido.")  # erro do usuário: repassa o motivo
        if body.get("code") == "engine_crashed":
            raise AnalysisFailed(502, "O motor estatístico caiu durante esta análise (possivelmente falta de memória) e foi reiniciado.")
        if s == 503:
            raise AnalysisFailed(503, "O motor estatístico está iniciando. Tente novamente em instantes.")
        raise AnalysisFailed(502, f"Erro no motor estatístico: {msg or 'falha interna'}")


# ---- montagem a partir da configuração ---------------------------------------
def build_service() -> AnalysisService:
    urls = settings.worker_urls
    client = httpx.AsyncClient(
        # leitura = limite da análise + folga para o worker recriar o motor depois de um timeout anterior
        timeout=httpx.Timeout(settings.analysis_timeout_s + 100, connect=3.0),
        limits=httpx.Limits(max_connections=max(4, len(urls) * 2)),
        headers={"Authorization": f"Bearer {settings.r_worker_token}"} if settings.r_worker_token else None,
    )
    remote = RemoteDatasets(settings.data_dir) if settings.r_worker_sync_datasets else None   # worker R em outra máquina

    async def send(url: str, payload: dict[str, Any]) -> WorkerReply:
        dataset_id = payload.get("dataset_id")
        try:
            if remote and isinstance(dataset_id, str):
                await remote.ensure(client, url, dataset_id)
            resp = await client.post(f"{url}/run", json=payload)
            if remote and isinstance(dataset_id, str) and is_dataset_missing(resp.status_code, resp.text):
                await remote.ensure(client, url, dataset_id, force=True)   # o edge descartou o arquivo (limite de cache)
                resp = await client.post(f"{url}/run", json=payload)
        except RemoteSyncError as exc:
            if exc.status == 503:
                raise ConnectFailure(exc.message) from exc   # worker remoto fora do ar: o pool o tira de circulação
            if exc.status == 504:
                raise TimeoutError(exc.message) from exc
            return WorkerReply(502, {"message": exc.message})
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ConnectFailure(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        try:
            body = resp.json()
        except ValueError:
            body = {"message": resp.text[:300]}
        return WorkerReply(resp.status_code, body)

    pool = WorkerPool(urls, send, max_queue=settings.analysis_queue_max, wait_s=settings.analysis_queue_wait_s, down_s=settings.worker_down_s)
    cache = ResultCache(settings.analysis_cache_entries, settings.analysis_cache_mb * 1024 * 1024)
    return AnalysisService(pool, cache, timeout_s=settings.analysis_timeout_s)


_service: AnalysisService | None = None


def get_service() -> AnalysisService:
    global _service
    if _service is None:
        _service = build_service()
    return _service


def reset_service() -> None:
    """Descarta o serviço (e o cache/estado do pool). Usado em testes e ao mudar a configuração."""
    global _service
    _service = None
