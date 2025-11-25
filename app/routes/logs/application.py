from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from common.schema import StringResponse
from . import service, schema
from routes.projects import application as project_app, service as project_service


async def get_errors(
    conn: AsyncSession, userid: int, projectid: int, limit: int, offset: int
) -> schema.ErrorSequenceResponse:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    return await service.get_errors(conn, projectid, limit, offset)


async def read_log(
    conn: AsyncSession,
    projectid: int,
    userid: int,
    logfileid: int,
    limit: int,
    offset: int,
) -> StringResponse:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    logfile = await project_service.get_logfile(conn, projectid, logfileid)
    with open(logfile.file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total_lines = len(lines)
    selected_lines = lines[offset : offset + limit]
    return StringResponse(
        data="".join(selected_lines) if selected_lines else "", total=total_lines
    )
