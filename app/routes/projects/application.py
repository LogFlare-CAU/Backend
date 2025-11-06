from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST

from . import schema, service, model
from fastapi import HTTPException
import os


async def add_logfile(
    conn: AsyncSession, project_id: int, item: schema.LogFileCreateParams
) -> model.LogFile:
    logpath = item.path
    if os.path.exists(logpath):
        return await service.add_logfile(conn, project_id, item)
    else:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="file not found")
