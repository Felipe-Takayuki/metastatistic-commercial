"""Transformações de dados no estilo Power Query: uma *receita* (lista de passos) vira SQL com uma CTE por passo.

Fluxo: a receita é validada e compilada aqui; o SQL resultante roda no MESMO sandbox das consultas do usuário
(`queries._sandbox`, só os datasets que ele pode ler, com filtro de linhas) e, ao salvar, passa por
`derive.create_dataset_from_query` — que materializa em Parquet e herda as restrições de acesso. Nada aqui lê arquivos
nem monta SQL a partir de texto do usuário sem escapar: identificadores vão entre aspas duplas e valores viram
literais tipados (número validado, texto escapado) ou a fórmula passa por uma lista de permissões do `sqlglot`.

O esquema (colunas e tipos) é descoberto passo a passo com `DESCRIBE` no próprio DuckDB, então os tipos são os reais
e os erros apontam o passo ("Passo 3: …").
"""
import json
import math
import re
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Union

import duckdb
import sqlglot
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from sqlglot import exp

from . import datasets, db, permissions, queries
from .datasets import sql_str

MAX_STEPS = 50
Ident = Annotated[str, StringConstraints(min_length=1, max_length=200)]
NewName = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class TransformError(ValueError):
    """Receita inválida (coluna inexistente, tipo errado, fórmula proibida…) -> HTTP 422."""


# ---------------------------------------------------------------------------------------------------------------------
# Modelo da receita
# ---------------------------------------------------------------------------------------------------------------------
class Operand(BaseModel):
    """Um valor: coluna, número, texto ou nulo (exatamente um)."""
    col: Ident | None = None
    num: float | None = None
    text: str | None = Field(default=None, max_length=500)
    null: bool | None = None

    @model_validator(mode="after")
    def _one(self):
        given = [x for x in (self.col, self.num, self.text, self.null) if x is not None]
        if len(given) != 1:
            raise ValueError("an operand needs exactly one of col, num, text, null")
        if self.num is not None and not math.isfinite(self.num):
            raise ValueError("number must be finite")
        return self


Operator = Literal["eq", "ne", "gt", "ge", "lt", "le", "contains", "not_contains", "starts_with", "ends_with",
                   "is_null", "not_null", "in", "not_in"]


class Condition(BaseModel):
    column: Ident
    operator: Operator
    value: str | None = Field(default=None, max_length=500)
    values: list[Annotated[str, StringConstraints(max_length=500)]] = Field(default_factory=list, max_length=200)


class SelectStep(BaseModel):
    op: Literal["select"]
    columns: list[Ident] = Field(min_length=1, max_length=500)
    mode: Literal["keep", "drop"] = "keep"


class RenameStep(BaseModel):
    op: Literal["rename"]
    mapping: dict[Ident, NewName] = Field(min_length=1, max_length=500)


class CastStep(BaseModel):
    op: Literal["cast"]
    column: Ident
    to: Literal["number", "integer", "text", "date", "boolean"]


class FilterStep(BaseModel):
    op: Literal["filter"]
    conditions: list[Condition] = Field(min_length=1, max_length=20)
    combine: Literal["and", "or"] = "and"


class SortKey(BaseModel):
    column: Ident
    desc: bool = False


class SortStep(BaseModel):
    op: Literal["sort"]
    keys: list[SortKey] = Field(min_length=1, max_length=10)


class DedupeStep(BaseModel):
    op: Literal["dedupe"]
    columns: list[Ident] = Field(default_factory=list, max_length=500)  # vazio = linha inteira


class DropNullsStep(BaseModel):
    op: Literal["drop_nulls"]
    columns: list[Ident] = Field(default_factory=list, max_length=500)  # vazio = qualquer coluna


class FillNullsStep(BaseModel):
    op: Literal["fill_nulls"]
    column: Ident
    how: Literal["value", "mean", "median"] = "value"
    value: str | None = Field(default=None, max_length=500)


class RowStatStep(BaseModel):
    op: Literal["row_stat"]
    name: NewName
    fn: Literal["mean", "sum", "min", "max", "count"]
    columns: list[Ident] = Field(min_length=2, max_length=30)
    require_all: bool = False  # true: se alguma coluna da linha for nula, o resultado é nulo


class ArithStep(BaseModel):
    op: Literal["arith"]
    name: NewName
    left: Operand
    operator: Literal["+", "-", "*", "/"]
    right: Operand


class MathStep(BaseModel):
    op: Literal["math"]
    name: NewName
    fn: Literal["round", "abs", "sqrt", "ln", "log10", "exp", "floor", "ceil", "square"]
    column: Ident
    digits: int = Field(default=0, ge=0, le=15)


class CondStep(BaseModel):
    op: Literal["cond"]
    name: NewName
    conditions: list[Condition] = Field(min_length=1, max_length=20)
    combine: Literal["and", "or"] = "and"
    then: Operand
    otherwise: Operand


class BinsStep(BaseModel):
    op: Literal["bins"]
    name: NewName
    column: Ident
    edges: list[float] = Field(min_length=1, max_length=50)
    labels: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=51)

    @field_validator("edges")
    @classmethod
    def _ascending(cls, v: list[float]) -> list[float]:
        if any(not math.isfinite(x) for x in v) or any(b <= a for a, b in zip(v, v[1:])):
            raise ValueError("edges must be finite and strictly increasing")
        return v


class ReplaceStep(BaseModel):
    op: Literal["replace"]
    name: NewName | None = None  # vazio = substitui na própria coluna
    column: Ident
    mapping: dict[Annotated[str, StringConstraints(max_length=200)], Annotated[str, StringConstraints(max_length=200)]] = Field(min_length=1, max_length=200)


class TextFnStep(BaseModel):
    op: Literal["text_fn"]
    name: NewName
    fn: Literal["upper", "lower", "trim", "length"]
    column: Ident


class ConcatStep(BaseModel):
    op: Literal["concat"]
    name: NewName
    columns: list[Ident] = Field(min_length=2, max_length=30)
    sep: str = Field(default="", max_length=20)


class DatePartStep(BaseModel):
    op: Literal["date_part"]
    name: NewName
    column: Ident
    part: Literal["year", "quarter", "month", "day", "week", "weekday", "year_month"]


class FormulaStep(BaseModel):
    op: Literal["formula"]
    name: NewName
    expr: str = Field(min_length=1, max_length=500)


Step = Annotated[
    Union[SelectStep, RenameStep, CastStep, FilterStep, SortStep, DedupeStep, DropNullsStep, FillNullsStep, RowStatStep,
          ArithStep, MathStep, CondStep, BinsStep, ReplaceStep, TextFnStep, ConcatStep, DatePartStep, FormulaStep],
    Field(discriminator="op"),
]


class Recipe(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    steps: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)


# ---------------------------------------------------------------------------------------------------------------------
# Tipos e literais
# ---------------------------------------------------------------------------------------------------------------------
_NUMERIC = re.compile(r"^(U?(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT)|FLOAT|DOUBLE|REAL|DECIMAL)", re.I)
_TEMPORAL = re.compile(r"^(DATE|TIMESTAMP)", re.I)


def is_numeric(dtype: str) -> bool:
    return bool(_NUMERIC.match(dtype))


def is_temporal(dtype: str) -> bool:
    return bool(_TEMPORAL.match(dtype))


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def num_lit(x: float) -> str:
    if not math.isfinite(x):
        raise TransformError("number must be finite")
    return str(int(x)) if float(x).is_integer() and abs(x) < 1e15 else repr(float(x))


Schema = dict[str, str]  # nome da coluna -> tipo (na ordem das colunas)


def _col(schema: Schema, name: str, *, need: str | None = None) -> str:
    if name not in schema:
        raise TransformError(f"coluna não encontrada: {name!r}")
    if need == "numeric" and not is_numeric(schema[name]):
        raise TransformError(f"a coluna {name!r} ({schema[name]}) não é numérica; converta o tipo antes")
    if need == "temporal" and not is_temporal(schema[name]):
        raise TransformError(f"a coluna {name!r} ({schema[name]}) não é uma data; converta o tipo antes")
    return q(name)


def _new_name(schema: Schema, name: str) -> str:
    name = name.strip()
    if not name or any(ord(c) < 32 for c in name):
        raise TransformError("o nome da nova coluna não pode ser vazio")
    if name.lower() in {c.lower() for c in schema}:
        raise TransformError(f"já existe uma coluna chamada {name!r}; escolha outro nome")
    return name


def _typed_literal(raw: str, dtype: str) -> str:
    """Valor digitado (texto) -> literal SQL do tipo da coluna."""
    if is_numeric(dtype):
        try:
            return num_lit(float(raw.strip().replace(",", ".")))
        except ValueError as exc:
            raise TransformError(f"{raw!r} não é um número") from exc
    if is_temporal(dtype):
        try:
            datetime.fromisoformat(raw.strip())
        except ValueError as exc:
            raise TransformError(f"{raw!r} não é uma data válida (use AAAA-MM-DD)") from exc
        return f"CAST({sql_str(raw.strip())} AS {'DATE' if dtype.upper().startswith('DATE') else 'TIMESTAMP'})"
    if dtype.upper() == "BOOLEAN":
        low = raw.strip().lower()
        if low in ("true", "verdadeiro", "sim", "1"):
            return "TRUE"
        if low in ("false", "falso", "não", "nao", "0"):
            return "FALSE"
        raise TransformError(f"{raw!r} não é verdadeiro/falso")
    return sql_str(raw)


def _condition(c: Condition, schema: Schema) -> str:
    col = _col(schema, c.column)
    dtype = schema[c.column]
    if c.operator == "is_null":
        return f"{col} IS NULL"
    if c.operator == "not_null":
        return f"{col} IS NOT NULL"
    if c.operator in ("in", "not_in"):
        if not c.values:
            raise TransformError(f"informe ao menos um valor para a condição sobre {c.column!r}")
        items = ", ".join(_typed_literal(v, dtype) for v in c.values)
        return f"{col} {'NOT ' if c.operator == 'not_in' else ''}IN ({items})"
    if c.value is None or (c.value.strip() == "" and is_numeric(dtype)):
        raise TransformError(f"informe um valor para a condição sobre {c.column!r}")
    if c.operator in ("contains", "not_contains", "starts_with", "ends_with"):
        text, needle = f"lower(CAST({col} AS VARCHAR))", f"lower({sql_str(c.value)})"
        return {
            "contains": f"strpos({text}, {needle}) > 0",
            "not_contains": f"strpos({text}, {needle}) = 0",
            "starts_with": f"starts_with({text}, {needle})",
            "ends_with": f"ends_with({text}, {needle})",
        }[c.operator]
    sym = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}[c.operator]
    return f"{col} {sym} {_typed_literal(c.value, dtype)}"


def _conditions(conds: list[Condition], combine: str, schema: Schema) -> str:
    return f" {combine.upper()} ".join(f"({_condition(c, schema)})" for c in conds)


def _operand_kind(o: Operand, schema: Schema) -> str | None:
    """Família do valor (número, data, texto, booleano) ou None para nulo, que combina com qualquer uma."""
    if o.null:
        return None
    if o.num is not None:
        return "num"
    if o.text is not None:
        return "text"
    dtype = schema.get(o.col or "")
    if dtype is None:
        raise TransformError(f"coluna não encontrada: {o.col!r}")
    return "num" if is_numeric(dtype) else "date" if is_temporal(dtype) else "bool" if dtype.upper() == "BOOLEAN" else "text"


def _operand(o: Operand, schema: Schema, *, need_numeric: bool = False) -> str:
    if o.col is not None:
        return _col(schema, o.col, need="numeric" if need_numeric else None)
    if o.num is not None:
        return num_lit(o.num)
    if need_numeric:
        raise TransformError("esta operação aceita só colunas numéricas e números")
    if o.text is not None:
        return sql_str(o.text)
    return "NULL"


# ---------------------------------------------------------------------------------------------------------------------
# Fórmula livre: lista de permissões sobre a árvore do sqlglot
# ---------------------------------------------------------------------------------------------------------------------
_FORMULA_NODES = (
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg, exp.Paren, exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT,
    exp.GTE, exp.LT, exp.LTE, exp.Is, exp.Null, exp.Boolean, exp.Literal, exp.Column, exp.Identifier, exp.Between, exp.In,
    exp.Like, exp.ILike, exp.Case, exp.If, exp.Coalesce, exp.Nullif, exp.Greatest, exp.Least, exp.Abs, exp.Round, exp.Floor,
    exp.Ceil, exp.Sqrt, exp.Ln, exp.Log, exp.Exp, exp.Pow, exp.Upper, exp.Lower, exp.Trim, exp.Length, exp.Substring,
    exp.Concat, exp.ConcatWs, exp.Year, exp.Month, exp.Day, exp.Quarter, exp.Cast, exp.TryCast, exp.DataType,
)
_FORMULA_TYPES = {"INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "VARCHAR", "TEXT", "DATE", "BOOLEAN", "SMALLINT", "TIMESTAMP"}


def compile_formula(expr: str, schema: Schema) -> str:
    try:
        parsed = [p for p in sqlglot.parse(expr, read="duckdb") if p is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise TransformError(f"fórmula inválida: {str(exc).splitlines()[0]}") from exc
    if len(parsed) != 1:
        raise TransformError("a fórmula deve ser uma única expressão")
    tree = parsed[0]
    by_lower: dict[str, str] = {}
    for name in schema:
        by_lower.setdefault(name.lower(), name)
    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node
        if not isinstance(node, _FORMULA_NODES):
            raise TransformError(f"construção não permitida na fórmula: {type(node).__name__}")
        if isinstance(node, exp.Column):
            if node.table:
                raise TransformError("use só o nome da coluna (sem tabela)")
            ident = node.this
            raw = ident.name if isinstance(ident, exp.Identifier) else str(ident)
            real = raw if raw in schema else by_lower.get(raw.lower())
            if real is None:
                raise TransformError(f"coluna não encontrada na fórmula: {raw!r}")
            node.set("this", exp.to_identifier(real, quoted=True))
        if isinstance(node, exp.DataType) and node.this.name not in _FORMULA_TYPES:
            raise TransformError(f"tipo não permitido na fórmula: {node.this.name}")
    return tree.sql(dialect="duckdb")


# ---------------------------------------------------------------------------------------------------------------------
# Compilação dos passos
# ---------------------------------------------------------------------------------------------------------------------
_CAST_TYPES = {"number": "DOUBLE", "integer": "BIGINT", "text": "VARCHAR", "date": "DATE", "boolean": "BOOLEAN"}


def _add_column(schema: Schema, prev: str, name: str, expr: str) -> str:
    return f"SELECT *, {expr} AS {q(_new_name(schema, name))} FROM {prev}"


def _fmt(x: float) -> str:
    return f"{x:g}"


def compile_step(step, schema: Schema, prev: str) -> str:
    """Corpo do SELECT desta etapa, lendo da etapa anterior (`prev`) com o esquema `schema`."""
    op = step.op
    if op == "select":
        for c in step.columns:
            _col(schema, c)
        if step.mode == "keep":
            return f"SELECT {', '.join(q(c) for c in step.columns)} FROM {prev}"
        if len(set(step.columns)) >= len(schema):
            raise TransformError("não é possível remover todas as colunas")
        return f"SELECT * EXCLUDE ({', '.join(q(c) for c in dict.fromkeys(step.columns))}) FROM {prev}"
    if op == "rename":
        for old in step.mapping:
            _col(schema, old)
        final = [step.mapping.get(c, c).strip() for c in schema]
        if any(not f for f in final):
            raise TransformError("o novo nome não pode ser vazio")
        if len({f.lower() for f in final}) != len(final):
            raise TransformError("os nomes resultantes ficariam repetidos")
        return f"SELECT {', '.join(f'{q(c)} AS {q(f)}' for c, f in zip(schema, final))} FROM {prev}"
    if op == "cast":
        col = _col(schema, step.column)
        return f"SELECT * REPLACE (TRY_CAST({col} AS {_CAST_TYPES[step.to]}) AS {col}) FROM {prev}"
    if op == "filter":
        return f"SELECT * FROM {prev} WHERE {_conditions(step.conditions, step.combine, schema)}"
    if op == "sort":
        keys = ", ".join(f"{_col(schema, k.column)} {'DESC' if k.desc else 'ASC'} NULLS LAST" for k in step.keys)
        return f"SELECT * FROM {prev} ORDER BY {keys}"
    if op == "dedupe":
        cols = step.columns or list(schema)
        part = ", ".join(_col(schema, c) for c in cols)
        # índice oculto: mantém a PRIMEIRA ocorrência e a ordem original das linhas (DISTINCT/QUALIFY puro reordenam)
        return (f"SELECT * EXCLUDE (__rn) FROM (SELECT *, ROW_NUMBER() OVER () AS __rn FROM {prev}) "
                f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY __rn) = 1 ORDER BY __rn")
    if op == "drop_nulls":
        cols = step.columns or list(schema)
        return f"SELECT * FROM {prev} WHERE " + " AND ".join(f"{_col(schema, c)} IS NOT NULL" for c in cols)
    if op == "fill_nulls":
        col = _col(schema, step.column)
        if step.how == "value":
            if step.value is None:
                raise TransformError("informe o valor de preenchimento")
            repl = _typed_literal(step.value, schema[step.column])
        else:
            _col(schema, step.column, need="numeric")
            repl = f"{'AVG' if step.how == 'mean' else 'MEDIAN'}({col}) OVER ()"
        return f"SELECT * REPLACE (COALESCE({col}, {repl}) AS {col}) FROM {prev}"
    if op == "row_stat":
        cols = [_col(schema, c, need="numeric") for c in step.columns]
        lst = ", ".join(f"CAST({c} AS DOUBLE)" for c in cols) if step.fn == "mean" else ", ".join(cols)
        fn = {"mean": "list_avg", "sum": "list_sum", "min": "list_min", "max": "list_max", "count": "list_count"}[step.fn]
        expr = f"{fn}([{lst}])"
        if step.require_all and step.fn != "count":
            expr = f"CASE WHEN {' OR '.join(f'{c} IS NULL' for c in cols)} THEN NULL ELSE {expr} END"
        return _add_column(schema, prev, step.name, expr)
    if op == "arith":
        left, right = _operand(step.left, schema, need_numeric=True), _operand(step.right, schema, need_numeric=True)
        if step.operator == "/":
            right = f"NULLIF({right}, 0)"  # divisão por zero -> nulo, não erro
        return _add_column(schema, prev, step.name, f"({left} {step.operator} {right})")
    if op == "math":
        col = _col(schema, step.column, need="numeric")
        expr = {
            "round": f"round({col}, {step.digits})", "abs": f"abs({col})", "floor": f"floor({col})", "ceil": f"ceil({col})",
            "exp": f"exp({col})", "square": f"({col} * {col})",
            "sqrt": f"CASE WHEN {col} < 0 THEN NULL ELSE sqrt({col}) END",          # fora do domínio -> nulo
            "ln": f"CASE WHEN {col} <= 0 THEN NULL ELSE ln({col}) END",
            "log10": f"CASE WHEN {col} <= 0 THEN NULL ELSE log10({col}) END",
        }[step.fn]
        return _add_column(schema, prev, step.name, expr)
    if op == "cond":
        kinds = {_operand_kind(o, schema) for o in (step.then, step.otherwise)} - {None}
        if len(kinds) > 1:
            raise TransformError("os valores 'então' e 'senão' precisam ser do mesmo tipo (ambos número, ambos texto…)")
        expr = (f"CASE WHEN {_conditions(step.conditions, step.combine, schema)} "
                f"THEN {_operand(step.then, schema)} ELSE {_operand(step.otherwise, schema)} END")
        return _add_column(schema, prev, step.name, expr)
    if op == "bins":
        col = _col(schema, step.column, need="numeric")
        n = len(step.edges)
        labels = step.labels or (
            [f"< {_fmt(step.edges[0])}"]
            + [f"{_fmt(a)} – {_fmt(b)}" for a, b in zip(step.edges, step.edges[1:])]
            + [f"≥ {_fmt(step.edges[-1])}"]
        )
        if len(labels) != n + 1:
            raise TransformError(f"informe {n + 1} rótulos para {n} limites (ou nenhum, para rótulos automáticos)")
        whens = " ".join(f"WHEN {col} < {num_lit(e)} THEN {sql_str(labels[i])}" for i, e in enumerate(step.edges))
        return _add_column(schema, prev, step.name, f"CASE WHEN {col} IS NULL THEN NULL {whens} ELSE {sql_str(labels[-1])} END")
    if op == "replace":
        col = _col(schema, step.column)
        text = f"CAST({col} AS VARCHAR)"
        whens = " ".join(f"WHEN {sql_str(a)} THEN {sql_str(b)}" for a, b in step.mapping.items())
        expr = f"CASE {text} {whens} ELSE {text} END"
        target = (step.name or step.column).strip()
        if target == step.column:
            return f"SELECT * REPLACE ({expr} AS {col}) FROM {prev}"
        return _add_column(schema, prev, target, expr)
    if op == "text_fn":
        text = f"CAST({_col(schema, step.column)} AS VARCHAR)"
        expr = {"upper": f"upper({text})", "lower": f"lower({text})", "trim": f"trim({text})", "length": f"length({text})"}[step.fn]
        return _add_column(schema, prev, step.name, expr)
    if op == "concat":
        parts = ", ".join(f"CAST({_col(schema, c)} AS VARCHAR)" for c in step.columns)
        return _add_column(schema, prev, step.name, f"concat_ws({sql_str(step.sep)}, {parts})")
    if op == "date_part":
        col = _col(schema, step.column, need="temporal")
        expr = {
            "year": f"year({col})", "quarter": f"quarter({col})", "month": f"month({col})", "day": f"day({col})",
            "week": f"weekofyear({col})", "weekday": f"isodow({col})", "year_month": f"strftime({col}, '%Y-%m')",
        }[step.part]
        return _add_column(schema, prev, step.name, expr)
    if op == "formula":
        return _add_column(schema, prev, step.name, compile_formula(step.expr, schema))
    raise TransformError(f"passo desconhecido: {op}")  # inalcançável: a união discriminada já recusa


# ---------------------------------------------------------------------------------------------------------------------
# Receita -> SQL
# ---------------------------------------------------------------------------------------------------------------------
@dataclass
class Compiled:
    sql: str
    schemas: list[Schema]  # esquema ANTES de cada passo (índice 0 = origem); o último é o resultado


def _describe(con, sql: str) -> Schema:
    return {r[0]: str(r[1]) for r in con.execute(f"DESCRIBE {sql}").fetchall()}


def compile_recipe(recipe: Recipe, user) -> Compiled:
    try:
        source = datasets.get_dataset(recipe.source_id)
    except datasets.DatasetNotFound as exc:
        raise TransformError(f"dataset de origem não encontrado: {recipe.source_id}") from exc
    if not permissions.can_read(user, source.id):
        raise TransformError(f"dataset de origem não encontrado: {recipe.source_id}")  # não confirma que existe
    con = queries._sandbox(permissions.visible_views(user))
    try:
        ctes = [f"__s0 AS (SELECT * FROM {q(source.table_name)})"]
        schema = _describe(con, f"WITH {ctes[0]} SELECT * FROM __s0")
        schemas = [schema]
        for i, step in enumerate(recipe.steps, 1):
            try:
                body = compile_step(step, schema, f"__s{i - 1}")
                ctes.append(f"__s{i} AS ({body})")
                schema = _describe(con, f"WITH {', '.join(ctes)} SELECT * FROM __s{i}")
            except TransformError as exc:
                raise TransformError(f"Passo {i} ({step.op}): {exc}") from exc
            except duckdb.Error as exc:
                raise TransformError(f"Passo {i} ({step.op}): {_friendly(exc)}") from exc
            schemas.append(schema)
        return Compiled(f"WITH {', '.join(ctes)} SELECT * FROM __s{len(recipe.steps)}", schemas)
    finally:
        con.close()


def _friendly(exc: Exception) -> str:
    msg = str(exc).splitlines()[0]
    if "Conversion Error" in msg or "Cannot mix" in msg or "Binder Error" in msg and "cast" in msg.lower():
        return f"tipos incompatíveis ({msg[:140]}); converta as colunas ou use valores do mesmo tipo"
    return msg[:200]


# ---------------------------------------------------------------------------------------------------------------------
# Receitas salvas (de onde cada dataset derivado veio)
# ---------------------------------------------------------------------------------------------------------------------
def save_recipe(dataset_id: str, recipe: Recipe, sql: str) -> None:
    with closing(db.connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO dataset_recipes VALUES (?,?,?,?)",
                    [dataset_id, recipe.model_dump_json(), sql, datetime.now(timezone.utc).isoformat()])


def get_recipe(dataset_id: str) -> dict | None:
    with closing(db.connect()) as con:
        row = con.execute("SELECT * FROM dataset_recipes WHERE dataset_id = ?", [dataset_id]).fetchone()
    if row is None:
        return None
    return {"recipe": json.loads(row["recipe_json"]), "sql": row["sql"], "created_at": row["created_at"]}


def forget_recipe(dataset_id: str) -> None:
    with closing(db.connect()) as con, con:
        con.execute("DELETE FROM dataset_recipes WHERE dataset_id = ?", [dataset_id])


def carry_measurements(new_id: str, source_id: str) -> None:
    """Colunas que seguem com o mesmo nome e tipo mantêm o nível de medida que o usuário escolheu na origem."""
    src, new = datasets.get_dataset(source_id), datasets.get_dataset(new_id)
    by_name = {c.name: c for c in src.columns}
    wanted = {c.name: by_name[c.name].measurement for c in new.columns
              if c.name in by_name and by_name[c.name].dtype == c.dtype and by_name[c.name].measurement != c.measurement}
    if wanted:
        datasets.update_measurements(new_id, wanted)
