from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import RelationshipDirection
from sqlalchemy.orm.attributes import NO_VALUE  # NO_VALUE는 여전히 필요합니다.


# get_attribute, PASSIVE_NO_FETCH는 더 이상 사용하지 않습니다.


def _serialize_value(value):
    """표준이 아닌 객체 타입(datetime, Decimal, UUID)을 직렬화 가능한 형태로 변환합니다."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(timespec="seconds")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


class Base(DeclarativeBase):
    """SQLAlchemy 모델을 딕셔너리로 직렬화하는 __iter__ 메서드를 제공하는 기본 클래스입니다."""

    def __iter__(self):
        mapper = inspect(self.__class__)
        state = inspect(self)  # 👈 인스턴스 상태를 가져옵니다.

        # 1) Columns (일반 속성)
        for column in mapper.columns:
            value = getattr(self, column.key)
            yield column.key, _serialize_value(value)

        # 2) Relationships (로드된 관계만 처리)
        for rel in mapper.relationships:
            # Many-to-One 관계는 보통 Foreign Key Column으로 처리되므로 무시합니다.
            if rel.direction == RelationshipDirection.MANYTOONE:
                continue

            # 로드 여부 확인:
            # state.was_accessed(key)는 속성이 이전에 접근되어 로드된 이력이 있는지 확인합니다.
            # 하지만 이는 Lazy Load가 발생했는지 여부를 알려줄 뿐, 현재 로드 상태를 정확히 보장하진 않습니다.
            # 가장 확실한 방법은, **NO_VALUE를 기본값으로 지정하여 값을 가져오는 것**입니다.
            # SQLAlchemy 2.0+에서 이는 Lazy Load를 발생시키지 않고 로드 여부를 체크하는 표준 방식입니다.

            # 여기서 getattr은 내부적으로 get_attribute를 호출하며,
            # NO_VALUE 기본값을 통해 로드되지 않았으면 즉시 NO_VALUE를 반환합니다.
            # 이는 이전에 사용하려던 get_attribute(..., PASSIVE_NO_FETCH)의 의도를 구현합니다.
            value = getattr(self, rel.key, NO_VALUE)

            # NO_VALUE가 반환되었다면, 관계는 로드되지 않았으므로 스킵합니다.
            if value is NO_VALUE:
                continue

            # --- 직렬화 로직 ---
            if value is None:
                yield rel.key, None
            elif rel.uselist:
                # To-Many 관계: 리스트 내의 각 객체를 재귀적으로 직렬화합니다.
                yield rel.key, [dict(v) for v in value]
            else:
                # To-One 관계: 관련된 객체의 PK만 추출합니다.
                related_mapper = inspect(rel.mapper.class_)
                pk_attrs = related_mapper.primary_key

                # PK가 하나면 PK 값 자체를, 여러 개면 PK 맵을 반환합니다.
                if len(pk_attrs) == 1:
                    yield rel.key, getattr(value, pk_attrs[0].name)
                else:
                    yield rel.key, {pk.name: getattr(value, pk.name) for pk in pk_attrs}