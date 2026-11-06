"""Cache determinístico LRU para resultados estatísticos."""
from collections import OrderedDict
import hashlib
import json
from typing import Any


def deterministic_cache_key(
    tenant_id: str,
    analysis: str,
    dataset_id: str,
    options: dict[str, Any] | None = None,
    columns: list[str] | None = None,
) -> str:
    """Gera chave determinística SHA-256 baseada em tenant, análise, dataset, opções e colunas."""
    raw = json.dumps(
        {
            "tenant_id": tenant_id or "default",
            "analysis": analysis,
            "dataset_id": dataset_id,
            "options": options or {},
            "columns": sorted(columns) if columns else [],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResultCache:
    """Cache LRU limitado por contagem máxima de entradas e tamanho máximo em bytes."""

    def __init__(self, max_entries: int = 256, max_bytes: int = 64 * 1024 * 1024):
        self._max_entries = max_entries
        self._max_bytes = max_bytes
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
        try:
            payload_str = json.dumps(body, separators=(",", ":"), default=str)
            size = len(payload_str.encode("utf-8"))
        except Exception:
            size = 1024

        if size > self._max_bytes:
            return

        if key in self._items:
            old_size, _ = self._items.pop(key)
            self._bytes -= old_size

        self._items[key] = (size, body)
        self._bytes += size

        while len(self._items) > self._max_entries or self._bytes > self._max_bytes:
            _, (old_size, _) = self._items.popitem(last=False)
            self._bytes -= old_size

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._items),
            "max_entries": self._max_entries,
            "bytes": self._bytes,
            "max_bytes": self._max_bytes,
            "hits": self.hits,
            "misses": self.misses,
        }

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0
        self.hits = 0
        self.misses = 0
