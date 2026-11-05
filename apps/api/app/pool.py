"""Pool de workers R: fila FIFO limitada, reenvio se um worker cair, e contabilidade fiel de quem está ocupado.

Regras:
  * cada worker atende UMA análise por vez (o motor R é de thread única);
  * quem chega com todos ocupados espera na fila (FIFO), até `max_queue` pessoas e até `wait_s` segundos;
  * a ESPERA pode ser cancelada pelo cliente (desistiu: sai da fila), mas o ENVIO ao worker não é abortado:
    o worker continua rodando a análise, então o slot só volta ao pool quando ela de fato termina;
  * worker que não aceita a conexão é marcado como "fora" por `down_s` e o pedido (que nunca chegou a ele)
    é reenviado a outro; worker que estoura o tempo de leitura também sai por `down_s`.
"""
import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


UNAVAILABLE = "O motor estatístico está indisponível no momento. Tente novamente em instantes."


class PoolError(Exception):
    """Erro do pool, já com o status HTTP e a mensagem (em português) que o cliente deve ver."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class QueueFull(PoolError):
    status_code = 429


class QueueTimeout(PoolError):
    status_code = 503


class NoWorkers(PoolError):
    status_code = 503


class WorkerTimeout(PoolError):
    status_code = 504


class ConnectFailure(Exception):
    """O worker não aceitou a conexão: o pedido NÃO chegou a ele, então é seguro reenviá-lo a outro."""


@dataclass
class WorkerReply:
    status: int
    body: dict[str, Any]


Send = Callable[[str, dict[str, Any]], Awaitable[WorkerReply]]


class WorkerPool:
    def __init__(self, urls: list[str], send: Send, *, max_queue: int, wait_s: float, down_s: float):
        if not urls:
            raise ValueError("at least one worker url is required")
        self._urls = list(urls)
        self._send = send
        self._max_queue = max_queue
        self._wait_s = wait_s
        self._down_s = down_s
        self._idle: deque[str] = deque(self._urls)
        self._waiters: deque[asyncio.Future[str]] = deque()
        self._down: set[str] = set()
        self.completed = 0
        self.rejected = 0

    # ---- estado ---------------------------------------------------------
    def status(self) -> dict[str, int]:
        busy = len(self._urls) - len(self._idle) - len(self._down)
        return {
            "workers": len(self._urls), "busy": busy, "down": len(self._down),
            "queued": len(self._waiters), "queue_max": self._max_queue,
            "completed": self.completed, "rejected": self.rejected,
        }

    # ---- aquisição / devolução -----------------------------------------
    async def _acquire(self) -> str:
        if len(self._down) == len(self._urls):
            raise NoWorkers(UNAVAILABLE)
        if self._idle:
            return self._idle.popleft()
        if len(self._waiters) >= self._max_queue:
            self.rejected += 1
            raise QueueFull(f"A fila de análises está cheia ({len(self._waiters)} aguardando). Tente novamente em instantes.")
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiters.append(fut)
        try:
            return await asyncio.wait_for(fut, self._wait_s)
        except BaseException as exc:
            if fut.done() and not fut.cancelled() and fut.exception() is None:
                self._hand_off(fut.result())  # fomos acordados bem na hora de desistir: devolve o worker, não o perde
            elif fut in self._waiters:
                self._waiters.remove(fut)
            if isinstance(exc, asyncio.TimeoutError):
                self.rejected += 1
                raise QueueTimeout(f"O motor estatístico está ocupado: a análise esperou mais de {self._wait_s:g} s na fila. Tente novamente em instantes.") from None
            raise

    def _hand_off(self, url: str) -> None:
        """Entrega o worker ao próximo da fila (sem passar pelo estado 'ocioso') ou o deixa ocioso."""
        while self._waiters:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_result(url)
                return
        self._idle.append(url)

    def _release(self, url: str, *, down: bool = False) -> None:
        if not down:
            self._hand_off(url)
            return
        self._down.add(url)
        if len(self._down) == len(self._urls):  # ninguém para atender: não faz sentido deixar a fila esperando
            err = NoWorkers(UNAVAILABLE)
            while self._waiters:
                fut = self._waiters.popleft()
                if not fut.done():
                    fut.set_exception(err)
        asyncio.get_running_loop().call_later(self._down_s, self._revive, url)

    def _revive(self, url: str) -> None:
        self._down.discard(url)
        self._hand_off(url)

    # ---- execução -------------------------------------------------------
    async def _call(self, url: str, payload: dict[str, Any]) -> WorkerReply:
        """Envia e SEMPRE devolve o slot ao terminar (roda como tarefa própria, protegida contra cancelamento)."""
        down = False
        try:
            reply = await self._send(url, payload)
            self.completed += 1
            return reply
        except ConnectFailure:
            down = True
            raise
        except (TimeoutError, asyncio.TimeoutError):
            down = True  # worker não respondeu no prazo: tira de circulação por um tempo
            raise
        finally:
            self._release(url, down=down)

    async def run(self, payload: dict[str, Any]) -> WorkerReply:
        attempts = max(1, min(2, len(self._urls)))
        for _ in range(attempts):
            url = await self._acquire()  # cancelável: quem desiste sai da fila
            task = asyncio.ensure_future(self._call(url, payload))
            task.add_done_callback(lambda t: t.cancelled() or t.exception())  # evita "exception never retrieved"
            try:
                return await asyncio.shield(task)  # cancelar o chamador NÃO aborta o envio; o slot volta quando terminar
            except ConnectFailure:
                continue
            except (TimeoutError, asyncio.TimeoutError):
                raise WorkerTimeout("O motor estatístico não respondeu a tempo. Tente novamente.") from None
        raise NoWorkers(UNAVAILABLE)
