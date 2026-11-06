"""Gerenciador de fila assíncrona com priorização (Enterprise/VIP vs Standard)."""
import asyncio
from datetime import datetime, timezone
from enum import Enum
import itertools
from typing import Any
import uuid

from app.cache import ResultCache, deterministic_cache_key
from app.config import settings
from app.engines.router import EngineRouter, default_router


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job:
    def __init__(
        self,
        job_id: str,
        payload: dict[str, Any],
        tenant_id: str = "default",
        priority: str = "standard",
        engine: str = "auto",
    ):
        self.job_id = job_id
        self.payload = payload
        self.tenant_id = tenant_id
        self.priority = priority.lower().strip()
        self.priority_level = 0 if self.priority in ("vip", "enterprise") else 1
        self.engine_requested = engine
        self.engine_used: str | None = None
        self.status = JobStatus.QUEUED
        self.progress: float = 0.0
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.done_event = asyncio.Event()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "analysis": self.payload.get("analysis", ""),
            "priority": self.priority,
            "engine_requested": self.engine_requested,
            "engine_used": self.engine_used,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


class QueueManager:
    """Gerenciador de tarefas com fila de prioridade e limitação de concorrência."""

    def __init__(
        self,
        max_concurrency: int = settings.max_concurrent_jobs,
        router: EngineRouter | None = None,
        cache: ResultCache | None = None,
    ):
        self.max_concurrency = max_concurrency
        self.router = router or default_router
        self.cache = cache
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._counter = itertools.count()
        self._workers: list[asyncio.Task] = []
        self._running_jobs = 0
        self._lock = asyncio.Lock()
        self._started = False

    def ensure_workers(self) -> None:
        """Garante que as tarefas operárias em background estejam ativas no event loop corrente."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        need_restart = False
        if not self._started or not self._workers:
            need_restart = True
        else:
            for w in self._workers:
                if w.done() or w.get_loop() != current_loop:
                    need_restart = True
                    break

        if need_restart:
            for w in self._workers:
                if not w.done():
                    w.cancel()
            self._workers.clear()
            self._queue = asyncio.PriorityQueue()
            for i in range(self.max_concurrency):
                task = current_loop.create_task(self._worker_loop(i))
                self._workers.append(task)
            self._started = True

    def reset(self) -> None:
        """Reseta a fila e encerra workers (útil entre execuções de testes)."""
        for w in self._workers:
            if not w.done():
                w.cancel()
        self._workers.clear()
        self._jobs.clear()
        self._queue = asyncio.PriorityQueue()
        self._started = False
        self._running_jobs = 0

    async def shutdown(self) -> None:
        """Encerra os workers graciosamente."""
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            try:
                _, _, job_id = await self._queue.get()
                job = self._jobs.get(job_id)
                if not job:
                    self._queue.task_done()
                    continue

                async with self._lock:
                    self._running_jobs += 1

                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc).isoformat()
                job.progress = 0.2

                try:
                    # Execução pelo roteador estatístico
                    result, engine_name = await self.router.execute(job.payload)
                    job.progress = 1.0
                    job.status = JobStatus.COMPLETED
                    job.engine_used = engine_name
                    job.result = result
                    job.completed_at = datetime.now(timezone.utc).isoformat()

                    # Armazena no cache se disponível
                    if self.cache is not None:
                        cache_key = deterministic_cache_key(
                            job.tenant_id,
                            job.payload.get("analysis", ""),
                            job.payload.get("dataset_id", ""),
                            job.payload.get("options", {}),
                            job.payload.get("columns", []),
                        )
                        self.cache.put(cache_key, result)

                except Exception as exc:
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    job.completed_at = datetime.now(timezone.utc).isoformat()
                finally:
                    async with self._lock:
                        self._running_jobs -= 1
                    job.done_event.set()
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def submit_job(
        self,
        payload: dict[str, Any],
        tenant_id: str = "default",
        priority: str = "standard",
        engine: str | None = None,
    ) -> Job:
        """Enfileira um novo job na fila de prioridade."""
        self.ensure_workers()
        job_id = uuid.uuid4().hex
        resolved_engine = engine or payload.get("engine") or settings.default_engine
        job_payload = {**payload, "engine": resolved_engine}

        job = Job(
            job_id=job_id,
            payload=job_payload,
            tenant_id=tenant_id,
            priority=priority,
            engine=resolved_engine,
        )
        self._jobs[job_id] = job

        # Insere na fila de prioridade (nível 0: VIP/Enterprise vem antes de 1: Standard)
        seq = next(self._counter)
        await self._queue.put((job.priority_level, seq, job_id))
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def wait_for_job(self, job_id: str, timeout_s: float = settings.analysis_timeout_s) -> Job:
        """Aguarda a conclusão do job até o tempo limite especificado."""
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' não encontrado.")
        try:
            await asyncio.wait_for(job.done_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tempo limite excedido ({timeout_s}s) aguardando execução do job {job_id}.")
        return job

    def status(self) -> dict[str, Any]:
        statuses = [j.status for j in self._jobs.values()]
        return {
            "total_jobs": len(self._jobs),
            "queued": statuses.count(JobStatus.QUEUED),
            "running": self._running_jobs,
            "completed": statuses.count(JobStatus.COMPLETED),
            "failed": statuses.count(JobStatus.FAILED),
            "max_concurrency": self.max_concurrency,
        }
