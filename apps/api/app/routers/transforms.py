from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import access, audit, auth, datasets, derive, permissions, plan_limits, queries, transforms
from ..schemas import Dataset
from ..security import current_user, require_editor, require_viewer

router = APIRouter(prefix="/transforms", tags=["transforms"], dependencies=[Depends(require_viewer)])


class PreviewIn(BaseModel):
    recipe: transforms.Recipe
    limit: int = Field(default=100, ge=1, le=1000)


class SaveIn(BaseModel):
    recipe: transforms.Recipe
    name: str = Field(min_length=1, max_length=120)


def _compile(recipe: transforms.Recipe, user: auth.User) -> transforms.Compiled:
    try:
        return transforms.compile_recipe(recipe, user)
    except transforms.TransformError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/preview")
def preview(body: PreviewIn, user: auth.User = Depends(current_user)) -> dict:
    """Roda a receita e devolve a prévia, o total de linhas, o SQL gerado e o esquema antes de cada passo."""
    compiled = _compile(body.recipe, user)
    try:
        result = queries.run_query(compiled.sql, body.limit, user=user)
        total = queries.run_query(f"SELECT COUNT(*) AS n FROM (\n{compiled.sql}\n) AS t", 1, user=user).rows[0][0]
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        **result.model_dump(), "total_rows": total, "sql": compiled.sql,
        "schemas": [[{"name": n, "dtype": t} for n, t in s.items()] for s in compiled.schemas],
    }


@router.post("/save", response_model=Dataset, status_code=201, dependencies=[Depends(require_editor)])
def save(body: SaveIn, user: auth.User = Depends(current_user),
         plan: plan_limits.Plan = Depends(plan_limits.check_can_create_dataset)) -> Dataset:
    """Materializa o resultado da receita como um dataset novo (herda as restrições de acesso da origem)."""
    compiled = _compile(body.recipe, user)
    try:
        created = derive.create_dataset_from_query(body.name, compiled.sql, user=user)
    except datasets.DatasetError as exc:
        raise HTTPException(422, str(exc)) from exc
    except queries.QueryError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan_limits.tag_dataset(created.id, plan.tenant_id)
    access.claim("dataset", created.id, user)
    permissions.apply_default_visibility(created.id)
    transforms.save_recipe(created.id, body.recipe, compiled.sql)
    transforms.carry_measurements(created.id, body.recipe.source_id)
    audit.log(user, "create", "dataset", created.id, f"{created.name} (receita, {len(body.recipe.steps)} passos)")
    return permissions.present([datasets.get_dataset(created.id)], user)[0]


@router.get("/recipes/{dataset_id}")
def get_recipe(dataset_id: str, user: auth.User = Depends(current_user)) -> dict | None:
    """Receita que gerou o dataset (para reabrir e editar), ou `null` se ele não veio de uma receita ou não é legível
    (mesma resposta nos dois casos: não confirma que um dataset restrito existe). `null` em vez de 404 porque a
    interface pergunta isto a cada dataset aberto, e um 404 normal poluiria o console do navegador."""
    return transforms.get_recipe(dataset_id) if permissions.can_read(user, dataset_id) else None
