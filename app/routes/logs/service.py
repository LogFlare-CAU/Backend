from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from common.sortingutils import get_sort_order
from routes.projects import service as project_service
from . import model, schema


async def log_error(
        conn: AsyncSession, projectid, item: schema.ErrorParams
) -> model.Errorlog:
    newerror = model.Errorlog()
    newerror.project_id = projectid
    newerror.errortype = item.errortype
    newerror.message = item.message
    newerror.level = item.level
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
        .order_by(model.Errorlog.timestamp.desc())
    )
    query = await conn.execute(stmt)
    return query.scalars().all()


async def get_errors_by_projectid(
        conn: AsyncSession, project_id, limit: int, offset: int, sort: str = "newest"
) -> Sequence[model.Errorlog]:
    orderby = get_sort_order(sort, model.Errorlog.timestamp, model.Errorlog.level)
    stmt = (
        select(model.Errorlog)
        .order_by(orderby)
        .where(model.Errorlog.project_id == project_id)
        .limit(limit)
        .offset(offset)
    )
    query = await conn.execute(stmt)
    return query.scalars().all()
