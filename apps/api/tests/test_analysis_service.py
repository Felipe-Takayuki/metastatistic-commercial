import asyncio

import pytest

from app.analysis_service import AnalysisFailed, AnalysisService, ResultCache, cache_key
from app.pool import WorkerReply, WorkerTimeout


async def settle(n: int = 10) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


class FakePool:
    def __init__(self, reply=None):
        self.reply = reply or WorkerReply(200, {"status": "complete", "results": {"x": 1}})
        self.payloads: list[dict] = []
        self.gate: asyncio.Event | None = None
        self.cancelled = 0

    def status(self):
        return {"workers": 1}

    async def run(self, payload):
        self.payloads.append(payload)
        try:
            if self.gate is not None:
                await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return self.reply


def svc(pool=None, entries=8, mb=1, timeout=60.0):
    pool = pool or FakePool()
    return AnalysisService(pool, ResultCache(entries, mb * 1024 * 1024), timeout_s=timeout), pool


async def test_second_identical_request_is_served_from_cache_without_touching_a_worker():
    s, pool = svc()
    a = await s.run("k1", {"i": 1})
    b = await s.run("k1", {"i": 1})
    assert a == b == {"status": "complete", "results": {"x": 1}}
    assert len(pool.payloads) == 1
    assert s.status()["cache"]["hits"] == 1
    await s.run("k2", {"i": 2})  # outra chave executa de novo
    assert len(pool.payloads) == 2


async def test_the_timeout_limit_is_sent_to_the_worker():
    s, pool = svc(timeout=42.0)
    await s.run("k", {"analysis": "T"})
    assert pool.payloads[0] == {"analysis": "T", "timeout_s": 42.0}


async def test_identical_requests_in_flight_share_one_execution():
    pool = FakePool()
    pool.gate = asyncio.Event()
    s, _ = svc(pool)
    t = [asyncio.create_task(s.run("same", {})) for _ in range(5)]
    await settle()
    assert len(pool.payloads) == 1 and s.status()["inflight"] == 1  # cinco pedidos, uma análise
    pool.gate.set()
    results = await asyncio.gather(*t)
    assert all(r == results[0] for r in results) and len(pool.payloads) == 1
    assert s.status()["inflight"] == 0


async def test_one_caller_giving_up_does_not_cancel_the_work_for_the_others():
    pool = FakePool()
    pool.gate = asyncio.Event()
    s, _ = svc(pool)
    a = asyncio.create_task(s.run("k", {}))
    b = asyncio.create_task(s.run("k", {}))
    await settle()
    a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await a
    pool.gate.set()
    assert (await b)["status"] == "complete" and pool.cancelled == 0


async def test_when_every_caller_gives_up_the_work_is_cancelled():
    pool = FakePool()
    pool.gate = asyncio.Event()
    s, _ = svc(pool)
    a = asyncio.create_task(s.run("k", {}))
    b = asyncio.create_task(s.run("k", {}))
    await settle()
    for t in (a, b):
        t.cancel()
    for t in (a, b):
        with pytest.raises(asyncio.CancelledError):
            await t
    await settle()
    assert pool.cancelled == 1  # ninguém quer o resultado: não ocupa fila/worker à toa
    assert s.status()["inflight"] == 0


async def test_failures_are_translated_and_never_cached():
    s, pool = svc()
    pool.reply = WorkerReply(422, {"status": "error", "message": "group: Maximum number of levels is 2. Variable x has 4 levels."})
    for _ in range(2):  # repetir prova que não ficou em cache
        with pytest.raises(AnalysisFailed) as e:
            await s.run("bad", {})
        assert e.value.status_code == 422 and "Maximum number of levels is 2" in e.value.message
    assert len(pool.payloads) == 2 and s.status()["cache"]["entries"] == 0


async def test_worker_timeout_becomes_504_with_the_limit_in_the_message():
    s, pool = svc(timeout=60.0)
    pool.reply = WorkerReply(504, {"status": "error", "code": "timeout", "message": "analysis exceeded the 60 s limit and was stopped"})
    with pytest.raises(WorkerTimeout) as e:
        await s.run("slow", {})
    assert e.value.status_code == 504 and "60 s" in e.value.message and s.status()["cache"]["entries"] == 0


@pytest.mark.parametrize("reply,status,fragment", [
    (WorkerReply(500, {"code": "engine_crashed", "message": "boom"}), 502, "caiu"),
    (WorkerReply(500, {"message": "falha interna x"}), 502, "falha interna x"),
    (WorkerReply(503, {"code": "engine_unavailable"}), 503, "iniciando"),
    (WorkerReply(500, "texto que não é dict"), 502, "falha interna"),  # corpo inesperado não derruba a API
])
async def test_other_worker_failures_map_to_clear_errors(reply, status, fragment):
    s, pool = svc()
    pool.reply = reply
    with pytest.raises(AnalysisFailed) as e:
        await s.run("k", {})
    assert e.value.status_code == status and fragment in e.value.message


async def test_non_complete_results_are_returned_but_not_cached():
    s, pool = svc()
    pool.reply = WorkerReply(200, {"status": "validationError", "results": {"errorMessage": "x"}})
    assert (await s.run("k", {}))["status"] == "validationError"
    await s.run("k", {})
    assert len(pool.payloads) == 2  # reexecuta: pode ser um estado transitório


# ---- cache ---------------------------------------------------------------
def test_lru_evicts_the_least_recently_used_and_reads_refresh_recency():
    c = ResultCache(max_entries=2, max_bytes=10_000)
    c.put("a", {"v": 1}); c.put("b", {"v": 2})
    assert c.get("a") == {"v": 1}  # a vira o mais recente
    c.put("c", {"v": 3})  # estoura: sai o menos recente (b), não o a
    assert c.get("b") is None and c.get("a") == {"v": 1} and c.get("c") == {"v": 3}


def test_cache_is_bounded_by_bytes_too_and_never_stores_an_oversized_result():
    c = ResultCache(max_entries=100, max_bytes=100)
    c.put("big", {"blob": "x" * 500})  # maior que o cache inteiro
    assert c.get("big") is None and c.stats()["bytes"] == 0
    c.put("a", {"v": "x" * 30}); c.put("b", {"v": "y" * 30}); c.put("c", {"v": "z" * 30})
    st = c.stats()
    assert st["bytes"] <= 100 and st["entries"] < 3  # expulsou para respeitar o limite de bytes
    c.put("small", {"v": 1})
    c.put("big2", {"blob": "x" * 500})  # resultado gigante não expulsa os que já estavam lá
    assert c.get("small") == {"v": 1}


def test_replacing_a_key_keeps_the_byte_accounting_exact():
    c = ResultCache(max_entries=5, max_bytes=10_000)
    c.put("k", {"v": "x" * 100})
    before = c.stats()["bytes"]
    c.put("k", {"v": "x" * 100})
    assert c.stats()["bytes"] == before and c.stats()["entries"] == 1


# ---- chave ---------------------------------------------------------------
def test_cache_key_ignores_dict_order_but_changes_with_anything_that_changes_the_result():
    base = dict(analysis="T", dataset_id="d", options={"a": 1, "b": [1, 2]}, columns=["x", "y"], measurement={"x": "scale", "y": "nominal"})
    k = cache_key(**base)
    assert k == cache_key(**{**base, "options": {"b": [1, 2], "a": 1}, "measurement": {"y": "nominal", "x": "scale"}})
    assert k != cache_key(**{**base, "measurement": {"x": "ordinal", "y": "nominal"}})  # mudar o nível de medida muda o resultado
    assert k != cache_key(**{**base, "options": {"a": 2, "b": [1, 2]}})
    assert k != cache_key(**{**base, "dataset_id": "e"})
    assert k != cache_key(**{**base, "columns": ["y", "x"]})
    assert k != cache_key(**{**base, "analysis": "U"})
