from datetime import time, datetime, date
from decimal import Decimal
from typing import Any, Type, Optional, List, get_origin, get_args
from uuid import UUID

from pydantic import BaseModel, Field, create_model, ConfigDict
from sqlalchemy import Enum as SAEnum, Column
from sqlalchemy.orm import DeclarativeMeta

from common.schema.common import APIResponse


# ---------- SA -> Python 타입 변환 ----------
def _py_type_from_sqla(col: Column) -> type[Any]:
    try:
        return col.type.python_type  # type: ignore[attr-defined]
    except Exception:
        pass
    t = col.type.__class__.__name__.lower()
    if "integer" in t or "bigint" in t or "smallint" in t:
        return int
    if "float" in t or "real" in t:
        return float
    if "numeric" in t or "decimal" in t:
        return Decimal
    if "bool" in t:
        return bool
    if "string" in t or "varchar" in t or "text" in t or "char" in t:
        return str
    if "uuid" in t:
        return UUID
    if "date" == t:
        return date
    if "datetime" in t or "timestamp" in t:
        return datetime
    if "time" == t:
        return time
    if isinstance(col.type, SAEnum) and getattr(col.type, "enum_class", None):
        return col.type.enum_class
    return Any


# ---------- SA -> Pydantic DTO ----------
def sqlalchemy_to_pydantic_with_comments(
    sa_model: Type[DeclarativeMeta],
    dto_name: str,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
    docstring: str | None = None,
    depth: int = 0,
    max_depth: int = 1,
) -> Type[BaseModel]:
    fields: dict[str, tuple[Any, Any]] = {}

    # --- 컬럼 ---
    for col in sa_model.__table__.columns:  # type: ignore[attr-defined]
        cname = col.name
        py_t = _py_type_from_sqla(col)
        desc = getattr(col, "comment", None)
        if col.nullable:
            fields[cname] = (Optional[py_t], Field(None, description=desc))
        else:
            fields[cname] = (py_t, Field(..., description=desc))

    # --- 관계 ---
    if depth < max_depth:
        for rel in sa_model.__mapper__.relationships:
            target_model = rel.entity.entity
            target_dto = get_or_create_dto(
                target_model,
                dto_name=None,
                docstring=None,
                depth=depth + 1,
                max_depth=max_depth,
            )
            desc = f"{rel.key} 관계"
            if rel.uselist:
                fields[rel.key] = (
                    List[target_dto],
                    Field(default_factory=list, description=desc),
                )
            else:
                fields[rel.key] = (
                    Optional[target_dto],
                    Field(default=None, description=desc),
                )

    if extra_fields:
        fields.update(extra_fields)

    PModel = create_model(dto_name, **fields, __doc__=docstring or dto_name)
    PModel.__name__ = dto_name
    PModel.model_config = ConfigDict(from_attributes=True, title=dto_name)
    return PModel


# ---------- DTO 재사용 레지스트리 ----------
# 🔥 캐시 키를 (모델, depth, max_depth, dto_name, bool(extra_fields)) 로 확장
_dto_registry: dict[tuple, type[BaseModel]] = {}


def get_or_create_dto(
    sa_model: Type[DeclarativeMeta],
    *,
    dto_name: str | None = None,
    docstring: str | None = None,
    depth: int = 0,
    max_depth: int = 1,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
):
    key = (
        sa_model,
        depth,
        max_depth,
        dto_name,
        frozenset(extra_fields.keys()) if extra_fields else None,
    )
    if key in _dto_registry:
        return _dto_registry[key]

    name = dto_name or f"{sa_model.__name__}DTO"
    dto = sqlalchemy_to_pydantic_with_comments(
        sa_model,
        name,
        extra_fields=extra_fields,
        docstring=docstring,
        depth=depth,
        max_depth=max_depth,
    )
    _dto_registry[key] = dto
    return dto


# ---------- 래퍼 생성 ----------
def make_named_response(
    sa_or_container: Any,
    response_name: str,
    *,
    dto_name: str | None = None,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
    return_inner: bool = False,
    docstring: str | None = None,
    max_depth: int = 1,
) -> Any:
    origin = get_origin(sa_or_container)

    def build_dto(sa_model: Any) -> Type[BaseModel]:
        return get_or_create_dto(
            sa_model,
            dto_name=dto_name,
            extra_fields=extra_fields,
            max_depth=max_depth,
        )

    if origin is None:
        InnerDTO = build_dto(sa_or_container)
        payload_type = InnerDTO
    else:
        args = get_args(sa_or_container)
        sa_model = args[0]
        InnerDTO = build_dto(sa_model)
        payload_type = List[InnerDTO]

    Wrapped = type(
        response_name,
        (APIResponse[payload_type],),
        {"__doc__": docstring or response_name},
    )
    Wrapped.__name__ = response_name
    Wrapped.model_config = ConfigDict(title=response_name)
    if hasattr(Wrapped, "model_rebuild"):
        Wrapped.model_rebuild()

    if return_inner:
        return Wrapped, InnerDTO
    return Wrapped
