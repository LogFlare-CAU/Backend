from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.sortingutils import LEVEL_ORDER, get_sort_order, level_order_expr

from routes.projects.model import LogFile
from routes.projects.service import get_logfile_by_name

from . import model, schema
from .enum import Level, Sort

RAW_MAX_LEN = 65_536


async def log_error(
        conn: AsyncSession, projectid, item: schema.ErrorParams
) -> model.Errorlog:
    newerror = model.Errorlog()
    newerror.project_id = projectid
    newerror.errortype = item.errortype
    newerror.message = item.message
    newerror.level = item.level.upper()
    newerror.raw = item.raw[:RAW_MAX_LEN] if item.raw is not None else None
    if item.logfile:
        logfile = await get_logfile_by_name(conn, projectid, item.logfile)
        newerror.logfile_id = logfile.id if logfile else None
    conn.add(newerror)
    await conn.commit()
    await conn.refresh(newerror)
    return newerror


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
        conds.append(E.timestamp >= f.since)
    if f.until is not None:
        conds.append(E.timestamp <= f.until)
    if ceiling is not None:
        conds.append(E.timestamp <= ceiling)
    if f.q:
        pattern = f"%{f.q.lower()}%"
        conds.append(
            or_(
                func.lower(E.message).like(pattern),
                func.lower(func.coalesce(E.errortype, "")).like(pattern),
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
    그룹 키: (project_id, coalesce(errortype, ''), message).
    """
    if not project_ids:
        return []
    E = model.Errorlog
    order = level_order_expr(func.upper(E.level))
    where = _event_conditions(project_ids, filters, ceiling)
    if filters.grouped:
        inner = (
            select(
                func.max(E.id).label("id"),
                func.count().label("occ"),
                func.min(E.timestamp).label("first_seen"),
                func.max(E.timestamp).label("last_seen"),
                func.max(order).label("lvl"),
            )
            .where(*where)
            .group_by(E.project_id, func.coalesce(E.errortype, ""), E.message)
        )
    else:
        inner = select(
            E.id.label("id"),
            func.count().label("occ"),
            E.timestamp.label("first_seen"),
            E.timestamp.label("last_seen"),
            order.label("lvl"),
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

    stmt = (
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
            func.upper(E.level).label("raw_level"),
            LogFile.file_name,
        )
        .join(E, E.id == sub.c.id)
        .outerjoin(LogFile, LogFile.id == E.logfile_id)
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
    )
    names = {i: lvl.value for i, lvl in enumerate(LEVEL_ORDER, start=1)}
    return [
        schema.LogEvent(
            id=r.id,
            project_id=r.project_id,
            logfile_id=r.logfile_id,
            logfile_name=r.file_name,
            errortype=r.errortype,
            message=r.message,
            level=names.get(r.lvl, r.raw_level),
            timestamp=r.last_seen,
            occurrences=r.occ,
            first_seen=r.first_seen,
            last_seen=r.last_seen,
        )
        for r in (await conn.execute(stmt)).all()
    ]


RECENT_IDS_LIMIT = 10


async def get_event_detail(
        conn: AsyncSession, error_id: int
) -> schema.LogEventDetail | None:
    """에러 한 건과 그가 속한 그룹(project, errortype, message)의 집계.

    id/raw 는 요청한 행의 값, level 은 그룹 최고 레벨, errortype/logfile 은
    그룹의 최신 행 기준이다.
    """
    E = model.Errorlog
    row = (await conn.execute(select(E).where(E.id == error_id))).scalar_one_or_none()
    if row is None:
        return None
    in_group = and_(
        E.project_id == row.project_id,
        func.coalesce(E.errortype, "") == (row.errortype or ""),
        E.message == row.message,
    )
    order = level_order_expr(func.upper(E.level))
    agg = (
        await conn.execute(
            select(
                func.count(),
                func.min(E.timestamp),
                func.max(E.timestamp),
                func.max(order),
                func.max(E.id),
            ).where(in_group)
        )
    ).one()
    occ, first_seen, last_seen, lvl, latest_id = agg
    latest = (
        await conn.execute(
            select(E.errortype, E.logfile_id, func.upper(E.level), LogFile.file_name)
            .outerjoin(LogFile, LogFile.id == E.logfile_id)
            .where(E.id == latest_id)
        )
    ).one()
    recent = (
        await conn.execute(
            select(E.id)
            .where(in_group, E.id != error_id)
            .order_by(E.id.desc())
            .limit(RECENT_IDS_LIMIT)
        )
    ).scalars().all()
    names = {i: lv.value for i, lv in enumerate(LEVEL_ORDER, start=1)}
    return schema.LogEventDetail(
        id=row.id,
        project_id=row.project_id,
        logfile_id=latest[1],
        logfile_name=latest[3],
        errortype=latest[0],
        message=row.message,
        level=names.get(lvl, latest[2]),
        timestamp=last_seen,
        occurrences=occ,
        first_seen=first_seen,
        last_seen=last_seen,
        raw=row.raw,
        recent_ids=list(recent),
    )
