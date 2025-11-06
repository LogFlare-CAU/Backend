from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from . import service, schema
from routes.projects import application as project_app


async def log_error(
    conn: AsyncSession, projectid: int, log: schema.ErrorParams
) -> None:
    res = await service.log_error(conn, projectid, log)
    # TODO: push notificatoin using firebase or other service
    return


async def get_errors(
    conn: AsyncSession, userid: int, projectid: int, limit: int, offset: int
) -> schema.ErrorSequenceResponse:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    return await service.get_errors(conn, projectid, limit, offset)
