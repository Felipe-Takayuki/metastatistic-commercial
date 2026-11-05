import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import datasets, derive, queries
from ..config import settings
from ..schemas import Dataset, DatasetFromQuery, DatasetPatch, QueryResult

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _http(exc: datasets.DatasetError) -> HTTPException:
    return HTTPException(404 if isinstance(exc, datasets.DatasetNotFound) else 422, str(exc))


@router.post("", response_model=Dataset, status_code=201)
def upload_dataset(file: UploadFile = File(...), name: str | None = Form(default=None)) -> Dataset:
    """Envia um CSV. O nome do arquivo nunca vira caminho em disco (só o nome lógico do dataset)."""
    display = (name or file.filename or "dataset").strip()[:120] or "dataset"
    limit = settings.max_upload_mb * 1024 * 1024
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = settings.data_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        size = 0
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB")
            tmp.write(chunk)
    try:
        return datasets.ingest_csv(tmp_path, display)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/from-query", response_model=Dataset, status_code=201)
def create_from_query(body: DatasetFromQuery) -> Dataset:
    """Salva o resultado de uma consulta SQL (somente leitura) como um novo dataset analisável."""
    try:
        return derive.create_dataset_from_query(body.name, body.sql)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=list[Dataset])
def list_datasets() -> list[Dataset]:
    return datasets.list_datasets()


@router.get("/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: str) -> Dataset:
    try:
        return datasets.get_dataset(dataset_id)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc


@router.patch("/{dataset_id}", response_model=Dataset)
def patch_dataset(dataset_id: str, patch: DatasetPatch) -> Dataset:
    """Corrige o nível de medida das colunas (define se o R trata como fator ou número)."""
    try:
        return datasets.update_measurements(dataset_id, patch.measurement)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc


@router.get("/{dataset_id}/preview", response_model=QueryResult)
def preview_dataset(dataset_id: str, limit: int = 50) -> QueryResult:
    try:
        ds = datasets.get_dataset(dataset_id)
        return queries.run_query(f'SELECT * FROM "{ds.table_name}"', limit=min(max(limit, 1), 1000))
    except (datasets.DatasetError, queries.QueryError) as exc:
        raise (_http(exc) if isinstance(exc, datasets.DatasetError) else HTTPException(422, str(exc))) from exc


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str) -> None:
    try:
        datasets.delete_dataset(dataset_id)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
