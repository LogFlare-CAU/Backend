import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.sortingutils import LEVEL_ORDER, get_sort_order, level_order_expr

from routes.projects.model import LogFile
from routes.projects.service import get_logfile_by_name

from . import model, schema
from .enum import Level, Sort


async def resolve_logfile_id(
        conn: AsyncSession, projectid: int, name: str | None
) -> int | None:
    """수신 바디의 logfile 이름을 프로젝트의 로그 파일 ID 로 (없으면 None)."""
    if not name:
        return None
    logfile = await get_logfile_by_name(conn, projectid, name)
    return logfile.id if logfile else None


async def get_errors(
        conn: AsyncSession, limit: int, offset: int, sort: str = "newest"
) -> Sequence[model.Errorlog]:
    orderby = get_sort_order(sort, model.Errorlog.timestamp, model.Errorlog.level)
    stmt = (
        select(model.Errorlog)
        .order_by(orderby)
        .limit(limit)
        .offset(offset)
    )
    query = await conn.execute(stmt)
    return query.scalars().all()


async def get_errors_for_projects(
        conn: AsyncSession,
        project_ids: Sequence[int],
        limit: int,
        offset: int,
        sort: str = "newest",
) -> Sequence[model.Errorlog]:
    if not project_ids:
        return []
    orderby = get_sort_order(sort, model.Errorlog.timestamp, model.Errorlog.level)
    stmt = (
        select(model.Errorlog)
        .where(model.Errorlog.project_id.in_(list(project_ids)))
        .order_by(orderby)
        .limit(limit)
        .offset(offset)
    )
    query = await conn.execute(stmt)
    return query.scalars().all()


async def get_errors_by_projectid(
        conn: AsyncSession, project_id, limit: int, offset: int, sort: str = "newest"
) -> Sequence[model.Errorlog]:
    orderby = get_sort_order(sort, model.Errorlog.timestamp, model.Errorlog.level)
    stmt = (
        select(model.Errorlog)
        .where(model.Errorlog.project_id == project_id)
        .order_by(orderby)
        .limit(limit)
        .offset(offset)
    )
    query = await conn.execute(stmt)
    return query.scalars().all()


async def count_levels(
        conn: AsyncSession, project_ids: Sequence[int], since: datetime
) -> dict[str, int]:
    """since 이후 레벨별 건수. 레거시 소문자 레벨은 upper()로 정규화한다."""
    counts = {lvl.value: 0 for lvl in LEVEL_ORDER}
    if not project_ids:
        return counts
    level = func.upper(model.Errorlog.level)
    stmt = (
        select(level, func.count())
        .where(
            model.Errorlog.project_id.in_(list(project_ids)),
            model.Errorlog.timestamp >= since,
        )
        .group_by(level)
    )
    for name, n in (await conn.execute(stmt)).all():
        if name in counts:
            counts[name] = n
    return counts


async def project_summaries(
        conn: AsyncSession, project_ids: Sequence[int], since: datetime
) -> list[schema.ProjectSummary]:
    if not project_ids:
        return []
    E = model.Errorlog
    level = func.upper(E.level)
    is_error = level.in_([Level.ERROR.value, Level.CRITICAL.value])
    in_window = E.timestamp >= since
    stmt = (
        select(
            E.project_id,
            func.coalesce(func.sum(case((is_error & in_window, 1), else_=0)), 0),
            func.coalesce(
                func.sum(case(((level == Level.WARNING.value) & in_window, 1), else_=0)),
                0,
            ),
            func.max(case((is_error, E.timestamp))),
        )
        .where(E.project_id.in_(list(project_ids)))
        .group_by(E.project_id)
    )
    rows = {r[0]: r for r in (await conn.execute(stmt)).all()}
    result = []
    for pid in project_ids:
        _, err, warn, last = rows.get(pid, (pid, 0, 0, None))
        result.append(
            schema.ProjectSummary(
                project_id=pid, error_count=err, warning_count=warn, last_error_at=last
            )
        )
    return result


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """오프셋이 있는 datetime 을 naive UTC 로 변환 (DB 는 naive UTC 저장)."""
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


@dataclass
class EventFilters:
    min_level: Level | None = None
    logfile_id: int | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = None
    sort: Sort = Sort.NEWEST
    grouped: bool = True


def _event_conditions(
        project_ids: Sequence[int], f: EventFilters, ceiling: datetime | None = None
) -> list:
    E = model.Errorlog
    conds = [E.project_id.in_(list(project_ids))]
    if f.min_level is not None:
        floor = LEVEL_ORDER.index(f.min_level) + 1
        conds.append(level_order_expr(func.upper(E.level)) >= floor)
    if f.logfile_id is not None:
        conds.append(E.logfile_id == f.logfile_id)
    if f.since is not None:
        conds.append(E.timestamp >= to_naive_utc(f.since))
    if f.until is not None:
        conds.append(E.timestamp <= to_naive_utc(f.until))
    if ceiling is not None:
        conds.append(E.timestamp <= ceiling)
    if f.q:
        needle = f.q.lower()
        conds.append(
            or_(
                func.lower(E.message).contains(needle, autoescape=True),
                func.lower(func.coalesce(E.errortype, "")).contains(
                    needle, autoescape=True
                ),
            )
        )
    return conds


async def newest_event_time(
        conn: AsyncSession, project_ids: Sequence[int], f: EventFilters
) -> datetime | None:
    if not project_ids:
        return None
    stmt = select(func.max(model.Errorlog.timestamp)).where(
        *_event_conditions(project_ids, f)
    )
    return (await conn.execute(stmt)).scalar()


def _group_key() -> list:
    """그룹 키: fingerprint 가 있으면 (project_id, fingerprint),
    없으면(옛 행) (project_id, coalesce(errortype, ''), message).

    fingerprint 가 있는 행은 나머지 키가 NULL 이 되어 fingerprint 로만 묶이고,
    없는 행은 fingerprint 가 NULL 로 같아서 옛 키로 묶인다.
    """
    E = model.Errorlog
    legacy = E.fingerprint.is_(None)
    return [
        E.project_id,
        E.fingerprint,
        case((legacy, func.coalesce(E.errortype, ""))),
        case((legacy, E.message)),
    ]


def _same_group(row: model.Errorlog) -> list:
    """row 와 같은 그룹(_group_key 기준)에 속하는 행 조건."""
    E = model.Errorlog
    if row.fingerprint is not None:
        return [E.project_id == row.project_id, E.fingerprint == row.fingerprint]
    return [
        E.project_id == row.project_id,
        E.fingerprint.is_(None),
        func.coalesce(E.errortype, "") == (row.errortype or ""),
        E.message == row.message,
    ]


def _group_aggregate(where: list):
    """그룹별 집계 서브쿼리 (그룹 키는 _group_key)."""
    E = model.Errorlog
    return (
        select(
            func.max(E.id).label("id"),
            func.count().label("occ"),
            func.min(E.timestamp).label("first_seen"),
            func.max(E.timestamp).label("last_seen"),
            func.max(level_order_expr(func.upper(E.level))).label("lvl"),
        )
        .where(*where)
        .group_by(*_group_key())
    )


def _event_select(sub):
    """집계 서브쿼리의 id(최신 행)에 행 정보와 로그 파일 이름을 붙인 select."""
    E = model.Errorlog
    return (
        select(
            sub.c.id,
            sub.c.occ,
            sub.c.first_seen,
            sub.c.last_seen,
            sub.c.lvl,
            E.project_id,
            E.logfile_id,
            E.errortype,
            E.message,
            E.fingerprint,
            func.upper(E.level).label("raw_level"),
            LogFile.file_name,
        )
        .join(E, E.id == sub.c.id)
        .outerjoin(LogFile, LogFile.id == E.logfile_id)
    )


def group_key(project_id: int, fingerprint: str | None, errortype: str | None, message: str) -> str:
    """_group_key 와 같은 기준의 문자열 키: fingerprint, 없으면 옛 키의 sha1."""
    if fingerprint is not None:
        return fingerprint
    legacy = f"p:{project_id}|t:{errortype or ''}|m:{message}"
    return hashlib.sha1(legacy.encode()).hexdigest()


def _to_event(r) -> schema.LogEvent:
    names = {i: lvl.value for i, lvl in enumerate(LEVEL_ORDER, start=1)}
    return schema.LogEvent(
        id=r.id,
        project_id=r.project_id,
        logfile_id=r.logfile_id,
        logfile_name=r.file_name,
        errortype=r.errortype,
        message=r.message,
        group_key=group_key(r.project_id, r.fingerprint, r.errortype, r.message),
        level=names.get(r.lvl, r.raw_level),
        timestamp=r.last_seen,
        occurrences=r.occ,
        first_seen=r.first_seen,
        last_seen=r.last_seen,
    )


async def list_events(
        conn: AsyncSession,
        project_ids: Sequence[int],
        filters: EventFilters,
        offset: int,
        limit: int,
        ceiling: datetime | None = None,
) -> list[schema.LogEvent]:
    """필터링/그룹핑된 이벤트 목록.

    ceiling 은 그룹핑 전 행 필터(timestamp <= ceiling)로 적용한다.
    """
    if not project_ids:
        return []
    E = model.Errorlog
    where = _event_conditions(project_ids, filters, ceiling)
    if filters.grouped:
        inner = _group_aggregate(where)
    else:
        inner = select(
            E.id.label("id"),
            func.count().label("occ"),
            E.timestamp.label("first_seen"),
            E.timestamp.label("last_seen"),
            level_order_expr(func.upper(E.level)).label("lvl"),
        ).where(*where).group_by(E.id)
    sub = inner.subquery()

    match filters.sort:
        case Sort.OLDEST:
            ordering = [sub.c.last_seen.asc(), sub.c.id.asc()]
        case Sort.HIGHEST:
            ordering = [sub.c.lvl.desc(), sub.c.last_seen.desc(), sub.c.id.desc()]
        case Sort.LOWEST:
            ordering = [sub.c.lvl.asc(), sub.c.last_seen.desc(), sub.c.id.desc()]
        case _:
            ordering = [sub.c.last_seen.desc(), sub.c.id.desc()]

    stmt = _event_select(sub).order_by(*ordering).limit(limit).offset(offset)
    return [_to_event(r) for r in (await conn.execute(stmt)).all()]



RECENT_IDS_LIMIT = 10


async def get_event_detail(
        conn: AsyncSession, error_id: int
) -> schema.LogEventDetail | None:
    """에러 한 건과 그가 속한 그룹의 집계 (list_events 와 같은 집계 사용).

    id/raw/occurred_at/row_level/logfile_* 는 요청한 행의 값이고,
    occurrences/first_seen/last_seen/level 은 그룹 전체의 값이다.
    """
    E = model.Errorlog
    row = (await conn.execute(select(E).where(E.id == error_id))).scalar_one_or_none()
    if row is None:
        return None
    in_group = _same_group(row)
    sub = _group_aggregate(in_group).subquery()
    event = _to_event((await conn.execute(_event_select(sub))).one())
    recent = (
        await conn.execute(
            select(E.id)
            .where(*in_group, E.id != error_id)
            .order_by(E.id.desc())
            .limit(RECENT_IDS_LIMIT)
        )
    ).scalars().all()
    return schema.LogEventDetail(
        **{
            **event.model_dump(),
            "id": row.id,
            "logfile_id": row.logfile_id,
            "logfile_name": row.logfile.file_name if row.logfile else None,
        },
        occurred_at=row.timestamp,
        row_level=(row.level or "").upper(),
        raw=row.raw,
        recent_ids=list(recent),
    )
