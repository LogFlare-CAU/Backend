from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase, RelationshipDirection
from sqlalchemy.orm.attributes import NO_VALUE


def _serialize_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


class Base(DeclarativeBase):
    __serialize_max_depth__: int = 1
    __serialize_include_manytoone_pk__: bool = False
    __serialize_exclude_keys__: set[str] = set()
    __serialize_exclude_predicate__: Callable[[str], bool] | None = None

    __serialize_global_blacklist__ = {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "secret",
        "api_key",
        "client_secret",
        "key",
    }

    @classmethod
    def _should_exclude(cls, key: str) -> bool:
        k = key.lower()
        if cls.__serialize_exclude_predicate__ and cls.__serialize_exclude_predicate__(
            k
        ):
            return True
        if k in (s.lower() for s in cls.__serialize_exclude_keys__):
            return True
        if k in cls.__serialize_global_blacklist__:
            return True
        if "token" in k:
            return True
        return False

    def _to_dict(self, *, depth: int, visited: set[int]) -> dict[str, Any]:
        mapper = inspect(self.__class__)
        state = inspect(self)
        out: dict[str, Any] = {}

        # 1) Columns (non-loading)
        for column in mapper.columns:
            key = column.key
            if self._should_exclude(key):
                continue
            if key in state.expired_attributes:
                continue
            attr = state.attrs[key]
            val = attr.loaded_value
            if val is NO_VALUE:
                continue
            out[key] = _serialize_value(val)

        # depth limit
        if depth >= getattr(self, "__serialize_max_depth__", 1):
            return out

        # 2) Relationships (only already-loaded)
        for rel in mapper.relationships:
            key = rel.key
            if self._should_exclude(key):
                continue

            if rel.direction == RelationshipDirection.MANYTOONE:
                if not getattr(self, "__serialize_include_manytoone_pk__", False):
                    continue

            attr = state.attrs[key]
            val = attr.loaded_value
            if val is NO_VALUE:
                continue  # not loaded -> skip

            if val is None:
                out[key] = None
                continue

            target_mapper = rel.mapper
            pk_cols = target_mapper.primary_key  # list[Column]

            if rel.uselist:
                items = []
                for child in val:
                    cid = id(child)
                    if cid in visited:
                        continue
                    visited.add(cid)

                    child_state = inspect(child)
                    if child_state.detached:
                        # detached면 안전하게 PK만
                        items.append(
                            {c.key: getattr(child, c.key, None) for c in pk_cols}
                        )
                        continue

                    if hasattr(child, "_to_dict"):
                        items.append(child._to_dict(depth=depth + 1, visited=visited))
                    else:
                        items.append(
                            {c.key: getattr(child, c.key, None) for c in pk_cols}
                        )
                out[key] = items
            else:
                child = val
                child_state = inspect(child)
                if child_state.detached:
                    if len(pk_cols) == 1:
                        out[key] = getattr(child, pk_cols[0].key, None)
                    else:
                        out[key] = {c.key: getattr(child, c.key, None) for c in pk_cols}
                else:
                    if hasattr(child, "_to_dict"):
                        out[key] = child._to_dict(depth=depth + 1, visited=visited)
                    else:
                        if len(pk_cols) == 1:
                            out[key] = getattr(child, pk_cols[0].key, None)
                        else:
                            out[key] = {
                                c.key: getattr(child, c.key, None) for c in pk_cols
                            }

        return out

    def __iter__(self):
        visited: set[int] = {id(self)}
        data = self._to_dict(depth=0, visited=visited)
        for k, v in data.items():
            yield k, v
