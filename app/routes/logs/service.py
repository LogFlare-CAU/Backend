from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from routes.projects import service as project_service
from . import model, schema


async def log_error(conn: AsyncSession, item: schema.ErrorParams) -> model.Errorlog:
    project = await project_service.get_project_by_name(conn, item.project)
    newerror = model.Errorlog()
    newerror.project_id = project.id
    newerror.message = item.message
    newerror.level = item.level
    conn.add(newerror)
    await conn.commit()
    await conn.refresh(newerror)
    return newerror


async def get_errors(
    conn: AsyncSession, project_id, limit: int, offset: int
) -> Sequence[model.Errorlog]:
    stmt = (
        select(model.Errorlog)
        .where(model.Errorlog.project_id == project_id)
        .limit(limit)
        .offset(offset)
    )
    query = await conn.execute(stmt)
    return query.scalars().all()
