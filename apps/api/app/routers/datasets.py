import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import access, audit, auth, datasets, derive, permissions, plan_limits, queries, transforms
from ..config import settings
from ..schemas import AccessConfig, Dataset, DatasetFromQuery, DatasetPatch, QueryResult

from ..security import can_modify, current_user, require_editor, require_viewer

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_viewer)])


def _http(exc: datasets.DatasetError) -> HTTPException:
    return HTTPException(404 if isinstance(exc, datasets.DatasetNotFound) else 422, str(exc))


_present = permissions.present


def _readable(dataset_id: str, user: auth.User) -> Dataset:
    """404 (não 403) para o que o usuário não pode ler: nem confirma que o dataset existe."""
    try:
        ds = datasets.get_dataset(dataset_id)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    if not permissions.can_read(user, dataset_id):
        audit.log(user, "denied", "dataset", dataset_id, "read")
        raise HTTPException(404, f"dataset not found: {dataset_id}")
    return ds


@router.post("", response_model=Dataset, status_code=201, dependencies=[Depends(require_editor)])
def upload_dataset(file: UploadFile = File(...), name: str | None = Form(default=None), user: auth.User = Depends(current_user),
                   plan: plan_limits.Plan = Depends(plan_limits.check_can_create_dataset)) -> Dataset:
    """Envia um CSV. O nome do arquivo nunca vira caminho em disco (só o nome lógico do dataset).
    O plano da organização limita quantos datasets existem e o tamanho de cada arquivo (402 com a mensagem do limite)."""
    display = (name or file.filename or "dataset").strip()[:120] or "dataset"
    limit = plan_limits.max_upload_bytes(plan)
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
                raise plan_limits.upload_too_big(plan)
            tmp.write(chunk)
    try:
        created = datasets.ingest_csv(tmp_path, display)
        access.claim("dataset", created.id, user)
        permissions.apply_default_visibility(created.id)
        audit.log(user, "create", "dataset", created.id, f"{created.name} (upload, {size / 1024:.1f} KB, plano {plan.name})")
        return _present([created], user)[0]
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/from-query", response_model=Dataset, status_code=201, dependencies=[Depends(require_editor)])
def create_from_query(body: DatasetFromQuery, user: auth.User = Depends(current_user),
                      plan: plan_limits.Plan = Depends(plan_limits.check_can_create_dataset)) -> Dataset:
    """Salva o resultado de uma consulta SQL (somente leitura) como um novo dataset analisável."""
    try:
        created = derive.create_dataset_from_query(body.name, body.sql, user=user)
        access.claim("dataset", created.id, user)
        permissions.apply_default_visibility(created.id)
        audit.log(user, "create", "dataset", created.id, f"{created.name} (derivado)")
        return _present([created], user)[0]
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=list[Dataset])
def list_datasets(user: auth.User = Depends(current_user)) -> list[Dataset]:
    return _present(datasets.list_datasets(), user)


@router.get("/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: str, user: auth.User = Depends(current_user)) -> Dataset:
    return _present([_readable(dataset_id, user)], user)[0]


@router.patch("/{dataset_id}", response_model=Dataset, dependencies=[Depends(can_modify("dataset", "dataset_id"))])
def patch_dataset(dataset_id: str, patch: DatasetPatch, user: auth.User = Depends(current_user)) -> Dataset:
    """Corrige o nível de medida das colunas (define se o R trata como fator ou número)."""
    try:
        return _present([datasets.update_measurements(dataset_id, patch.measurement)], user)[0]
    except datasets.DatasetError as exc:
        raise _http(exc) from exc


@router.get("/{dataset_id}/preview", response_model=QueryResult)
def preview_dataset(dataset_id: str, limit: int = 50, user: auth.User = Depends(current_user)) -> QueryResult:
    ds = _readable(dataset_id, user)
    try:
        return queries.run_query(f'SELECT * FROM "{ds.table_name}"', limit=min(max(limit, 1), 1000), user=user)
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{dataset_id}", status_code=204, dependencies=[Depends(can_modify("dataset", "dataset_id"))])
def delete_dataset(dataset_id: str, user: auth.User = Depends(current_user)) -> None:
    try:
        name = datasets.get_dataset(dataset_id).name
        datasets.delete_dataset(dataset_id)
        access.forget("dataset", dataset_id)
        permissions.forget_dataset(dataset_id)
        transforms.forget_recipe(dataset_id)
        audit.log(user, "delete", "dataset", dataset_id, name)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc


@router.get("/{dataset_id}/access", response_model=AccessConfig, dependencies=[Depends(can_modify("dataset", "dataset_id"))])
def get_access(dataset_id: str) -> AccessConfig:
    """Configuração de acesso (quem lê) e de linhas. Só o dono e administradores."""
    try:
        datasets.get_dataset(dataset_id)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    return AccessConfig(**permissions.get_config(dataset_id))


@router.put("/{dataset_id}/access", response_model=AccessConfig, dependencies=[Depends(can_modify("dataset", "dataset_id"))])
def put_access(dataset_id: str, body: AccessConfig, user: auth.User = Depends(current_user)) -> AccessConfig:
    try:
        cfg = permissions.set_config(dataset_id, body.restricted, body.user_ids, body.rls.model_dump() if body.rls else None)
    except datasets.DatasetError as exc:
        raise _http(exc) from exc
    except permissions.AccessConfigError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.log(user, "set_access", "dataset", dataset_id,
              f"restrito={cfg['restricted']} leitores={len(cfg['user_ids'])} linhas={'sim' if cfg['rls'] else 'não'}")
    return AccessConfig(**cfg)
