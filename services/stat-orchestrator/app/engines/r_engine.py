"""Adaptador para os workers R existentes (jaspTools / r-worker)."""
import asyncio
from typing import Any
import httpx

from app.config import settings
from app.engines.base import StatisticalEngine
from app.remote_datasets import RemoteDatasets, RemoteSyncError, is_dataset_missing


class REngineError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class RStatisticalEngine(StatisticalEngine):
    """Adaptador de microsserviço para clusters de workers R."""

    def __init__(self, urls: list[str] | None = None, timeout_s: float | None = None):
        self._urls = urls or settings.worker_urls
        self._timeout_s = timeout_s or settings.analysis_timeout_s
        self._next_worker_idx = 0
        self._lock = asyncio.Lock()
        self._remote = RemoteDatasets(settings.data_dir) if settings.r_worker_sync_datasets else None   # worker R em outra máquina

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.r_worker_token}"} if settings.r_worker_token else {}

    @property
    def name(self) -> str:
        return "r"

    def supports(self, analysis: str) -> bool:
        # O motor R é generalista e suporta todas as análises JASP e análises R custom
        return True

    async def _pick_worker_url(self) -> str:
        async with self._lock:
            if not self._urls:
                raise REngineError(503, "Nenhum worker R configurado.")
            url = self._urls[self._next_worker_idx % len(self._urls)]
            self._next_worker_idx += 1
            return url

    async def health(self) -> dict[str, Any]:
        worker_statuses = {}
        healthy_count = 0

        async with httpx.AsyncClient(timeout=3.0, headers=self._auth_headers()) as client:
            for url in self._urls:
                try:
                    resp = await client.get(f"{url}/health")
                    is_ok = resp.status_code == 200
                    worker_statuses[url] = "healthy" if is_ok else f"status_{resp.status_code}"
                    if is_ok:
                        healthy_count += 1
                except Exception as exc:
                    worker_statuses[url] = f"unreachable ({type(exc).__name__})"

        overall = "healthy" if healthy_count > 0 else "degraded"
        if not self._urls:
            overall = "unconfigured"

        return {
            "status": overall,
            "engine": "r_worker_adapter",
            "workers_total": len(self._urls),
            "workers_healthy": healthy_count,
            "workers": worker_statuses,
        }

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker_url = await self._pick_worker_url()
        raw_timeout = payload.get("timeout_s")
        timeout = float(raw_timeout) if raw_timeout is not None else float(self._timeout_s)

        req_payload = {**payload, "timeout_s": timeout}

        dataset_id = req_payload.get("dataset_id")
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout + 30.0, connect=5.0), headers=self._auth_headers()) as client:
            try:
                if self._remote and isinstance(dataset_id, str):
                    await self._remote.ensure(client, worker_url, dataset_id)
                resp = await client.post(f"{worker_url}/run", json=req_payload)
                if self._remote and isinstance(dataset_id, str) and is_dataset_missing(resp.status_code, resp.text):
                    await self._remote.ensure(client, worker_url, dataset_id, force=True)   # o edge descartou o arquivo (limite de cache)
                    resp = await client.post(f"{worker_url}/run", json=req_payload)
            except RemoteSyncError as exc:
                raise REngineError(exc.status, exc.message) from exc
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise REngineError(503, f"Falha ao conectar ao worker R ({worker_url}): {exc}") from exc
            except httpx.TimeoutException as exc:
                raise REngineError(504, f"Tempo limite ({timeout}s) excedido no worker R.") from exc
            except Exception as exc:
                raise REngineError(502, f"Erro inesperado de comunicação com worker R: {exc}") from exc

        try:
            body = resp.json()
        except Exception:
            raise REngineError(resp.status_code, f"Resposta inválida do worker R: {resp.text[:200]}")

        if resp.status_code != 200:
            msg = body.get("message") or body.get("error") or "Erro retornado pelo worker R"
            raise REngineError(resp.status_code, msg)

        return body
