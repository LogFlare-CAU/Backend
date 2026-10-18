from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.sortingutils import get_sort_order

from routes.projects.service import get_logfile_by_name

from . import model, schema

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
