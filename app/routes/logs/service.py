from datetime import datetime
from typing import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.sortingutils import LEVEL_ORDER, get_sort_order

from routes.projects.service import get_logfile_by_name

from . import model, schema
from .enum import Level

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
