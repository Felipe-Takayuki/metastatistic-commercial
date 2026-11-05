import asyncio

import pytest

from app.pool import (
    ConnectFailure, NoWorkers, QueueFull, QueueTimeout, WorkerPool, WorkerReply, WorkerTimeout,
)


async def settle(n: int = 10) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


class Fake:
    """Workers de mentira: cada análise `i` fica parada num portão até o teste liberá-lo."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []
        self.active: dict[str, int] = {}
        self.max_total = 0
        self.gates: dict[int, asyncio.Event] = {}
        self.fail: dict[str, Exception] = {}
        self.fail_after_gate: dict[str, Exception] = {}

    def gate(self, i: int) -> asyncio.Event:
        return self.gates.setdefault(i, asyncio.Event())

    async def send(self, url, payload):
        i = payload["i"]
        self.calls.append((url, i))
        self.active[url] = self.active.get(url, 0) + 1
        assert self.active[url] == 1, f"{url} recebeu duas análises ao mesmo tempo (o motor R é de thread única)"
        self.max_total = max(self.max_total, sum(self.active.values()))
        try:
            if url in self.fail:
                raise self.fail[url]
            if i in self.gates:
                await self.gates[i].wait()
            if url in self.fail_after_gate:
                raise self.fail_after_gate[url]
            return WorkerReply(200, {"status": "complete", "i": i, "url": url})
        finally:
            self.active[url] -= 1


def make(urls, fake, **kw):
    kw = {"max_queue": 10, "wait_s": 5.0, "down_s": 0.05, **kw}
    return WorkerPool(urls, fake.send, **kw)


async def test_concurrency_never_exceeds_the_number_of_workers_and_is_fifo():
    fake = Fake()
    pool = make(["A", "B"], fake)
    for i in range(5):
        fake.gate(i)
    tasks = [asyncio.create_task(pool.run({"i": i})) for i in range(5)]
    await settle()
    s = pool.status()
    assert (s["busy"], s["queued"]) == (2, 3)
    assert [i for _, i in fake.calls] == [0, 1]
    for i in range(5):  # libera um por vez: o próximo da fila entra, na ordem de chegada
        fake.gate(i).set()
        await settle()
    results = await asyncio.gather(*tasks)
    assert [r.body["i"] for r in results] == [0, 1, 2, 3, 4]
    assert [i for _, i in fake.calls] == [0, 1, 2, 3, 4]  # FIFO
    assert fake.max_total == 2
    assert pool.status()["busy"] == 0 and pool.status()["queued"] == 0


async def test_queue_full_is_429_and_does_not_disturb_the_others():
    fake = Fake()
    pool = make(["A"], fake, max_queue=2)
    for i in range(3):
        fake.gate(i)
    t = [asyncio.create_task(pool.run({"i": i})) for i in range(3)]  # 0 roda; 1 e 2 esperam (fila = 2)
    await settle()
    with pytest.raises(QueueFull) as e:
        await pool.run({"i": 3})
    assert e.value.status_code == 429 and "fila" in e.value.message
    assert pool.status()["rejected"] == 1 and pool.status()["queued"] == 2
    for i in range(3):
        fake.gate(i).set()
        await settle()
    assert [r.body["i"] for r in await asyncio.gather(*t)] == [0, 1, 2]


async def test_waiting_too_long_is_503_and_leaves_the_queue():
    fake = Fake()
    pool = make(["A"], fake, wait_s=0.05)
    fake.gate(0)
    first = asyncio.create_task(pool.run({"i": 0}))
    await settle()
    with pytest.raises(QueueTimeout) as e:
        await pool.run({"i": 1})
    assert e.value.status_code == 503 and "0.05" in e.value.message
    assert pool.status()["queued"] == 0  # quem desistiu por tempo não fica na fila
    fake.gate(0).set()
    await first
    assert pool.status()["busy"] == 0


async def test_client_that_gives_up_while_queued_leaves_the_queue_and_is_never_served():
    fake = Fake()
    pool = make(["A"], fake)
    fake.gate(0)
    first = asyncio.create_task(pool.run({"i": 0}))
    waiting = asyncio.create_task(pool.run({"i": 1}))
    await settle()
    assert pool.status()["queued"] == 1
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert pool.status()["queued"] == 0
    fake.gate(0).set()
    await first
    await settle()
    assert pool.status()["busy"] == 0  # o worker ficou ocioso: não foi "entregue" a quem desistiu
    assert [i for _, i in fake.calls] == [0]  # a análise 1 nunca foi executada
    assert (await pool.run({"i": 2})).body["i"] == 2


async def test_client_that_gives_up_while_running_does_not_free_the_slot_early():
    """A análise continua no worker; se o slot voltasse ao pool, o worker receberia trabalho enquanto ocupado."""
    fake = Fake()
    pool = make(["A"], fake)
    fake.gate(0)
    fake.gate(1)
    running = asyncio.create_task(pool.run({"i": 0}))
    queued = asyncio.create_task(pool.run({"i": 1}))
    await settle()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    await settle()
    assert pool.status()["busy"] == 1 and pool.status()["queued"] == 1  # ainda ocupado; o da fila continua esperando
    assert [i for _, i in fake.calls] == [0]
    fake.gate(0).set()  # a análise 0 termina de fato -> só agora o worker passa ao próximo
    await settle()
    assert [i for _, i in fake.calls] == [0, 1]
    fake.gate(1).set()
    assert (await queued).body["i"] == 1
    assert pool.status()["busy"] == 0


async def test_unreachable_worker_is_skipped_retried_elsewhere_and_comes_back():
    fake = Fake()
    fake.fail["A"] = ConnectFailure("recusou")
    pool = make(["A", "B"], fake, down_s=0.05)
    reply = await pool.run({"i": 0})
    assert reply.body["url"] == "B"  # A falhou na conexão: o pedido foi reenviado a B
    assert [u for u, _ in fake.calls] == ["A", "B"]
    assert pool.status()["down"] == 1
    assert (await pool.run({"i": 1})).body["url"] == "B"
    assert [u for u, _ in fake.calls] == ["A", "B", "B"]  # A não foi tentado de novo durante o castigo
    del fake.fail["A"]
    await asyncio.sleep(0.1)
    assert pool.status()["down"] == 0  # A voltou à circulação
    fake.gate(2)
    fake.gate(3)
    t2 = asyncio.create_task(pool.run({"i": 2}))
    t3 = asyncio.create_task(pool.run({"i": 3}))
    await settle()
    assert {u for u, i in fake.calls if i in (2, 3)} == {"A", "B"}  # e já recebe trabalho
    fake.gate(2).set(); fake.gate(3).set()
    await asyncio.gather(t2, t3)


async def test_all_workers_down_fails_fast_and_wakes_the_queue_instead_of_making_it_wait():
    fake = Fake()
    pool = make(["A"], fake, wait_s=30, down_s=5)
    fake.gate(0)
    fake.fail_after_gate["A"] = ConnectFailure("caiu")
    first = asyncio.create_task(pool.run({"i": 0}))
    second = asyncio.create_task(pool.run({"i": 1}))  # esperando na fila
    await settle()
    fake.gate(0).set()
    t0 = asyncio.get_running_loop().time()
    for t in (first, second):
        with pytest.raises(NoWorkers) as e:
            await asyncio.wait_for(t, 2)
        assert e.value.status_code == 503
    assert asyncio.get_running_loop().time() - t0 < 1  # não esperou os 30 s
    with pytest.raises(NoWorkers):
        await pool.run({"i": 2})  # e novos pedidos falham de imediato


async def test_read_timeout_is_504_and_takes_the_worker_out_for_a_while():
    fake = Fake()
    fake.fail["A"] = TimeoutError("sem resposta")
    pool = make(["A", "B"], fake)
    with pytest.raises(WorkerTimeout) as e:
        await pool.run({"i": 0})
    assert e.value.status_code == 504
    assert pool.status()["down"] == 1
    assert (await pool.run({"i": 1})).body["url"] == "B"  # o seguinte vai para o worker saudável


async def test_unexpected_error_propagates_but_the_slot_is_released():
    fake = Fake()
    fake.fail["A"] = RuntimeError("conexão cortada no meio")
    pool = make(["A"], fake)
    with pytest.raises(RuntimeError):
        await pool.run({"i": 0})
    assert pool.status()["busy"] == 0 and pool.status()["down"] == 0
    del fake.fail["A"]
    assert (await pool.run({"i": 1})).body["i"] == 1


def test_pool_requires_at_least_one_worker():
    with pytest.raises(ValueError):
        WorkerPool([], Fake().send, max_queue=1, wait_s=1, down_s=1)
