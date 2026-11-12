"""Worker R em OUTRA máquina: envia o Parquet do dataset antes da análise.

No modo normal o worker R lê `DATA_DIR/datasets/<id>.parquet` de um volume compartilhado. Com o worker remoto (ver
engines/r-worker-edge) esse volume não existe, então o arquivo é enviado ao edge (`PUT /datasets/<id>`) uma vez por worker;
as análises seguintes só reaproveitam. Os datasets são imutáveis (o id nunca muda de conteúdo), então "já enviado" basta.
Se o edge descartou o arquivo (limite de cache), o worker responde "dataset not found" e quem chama chama `ensure(force=True)`.
"""
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

CHUNK = 1024 * 1024
UPLOAD_TIMEOUT = httpx.Timeout(900.0, connect=5.0)


class RemoteSyncError(Exception):
    """Falha ao enviar o dataset ao worker remoto. `status` é o HTTP que o chamador deve devolver."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def is_dataset_missing(status: int, text: str) -> bool:
    return status == 400 and "dataset not found" in text


async def _chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as f:
        while chunk := await asyncio.to_thread(f.read, CHUNK):
            yield chunk


class RemoteDatasets:
    def __init__(self, data_dir: Path | str):
        self._dir = Path(data_dir) / "datasets"
        self._synced: set[tuple[str, str]] = set()
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def forget(self) -> None:
        self._synced.clear()

    async def ensure(self, client: httpx.AsyncClient, worker_url: str, dataset_id: str, *, force: bool = False) -> None:
        path = self._dir / f"{dataset_id}.parquet"
        if not path.is_file():
            return   # não existe aqui: o worker responde o erro de sempre ("dataset not found")
        key = (worker_url, dataset_id)
        if not force and key in self._synced:
            return
        async with self._locks.setdefault(key, asyncio.Lock()):   # duas análises do mesmo dataset não enviam duas vezes
            if not force and key in self._synced:
                return
            size = path.stat().st_size
            try:
                if not force:
                    info = await client.get(f"{worker_url}/datasets/{dataset_id}", timeout=10.0)
                    if info.status_code == 200 and info.json().get("size") == size:
                        self._synced.add(key)
                        return
                    if info.status_code == 401:
                        raise RemoteSyncError(502, "O worker R remoto recusou o token (R_WORKER_TOKEN).")
                resp = await client.put(f"{worker_url}/datasets/{dataset_id}", content=_chunks(path), headers={"content-length": str(size)}, timeout=UPLOAD_TIMEOUT)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise RemoteSyncError(503, f"Worker R remoto inacessível: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise RemoteSyncError(504, "Tempo esgotado ao enviar o dataset ao worker R remoto.") from exc
            if resp.status_code == 401:
                raise RemoteSyncError(502, "O worker R remoto recusou o token (R_WORKER_TOKEN).")
            if resp.status_code not in (200, 201):
                raise RemoteSyncError(502, f"O worker R remoto não aceitou o dataset (HTTP {resp.status_code}).")
            self._synced.add(key)
