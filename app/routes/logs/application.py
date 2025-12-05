from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from starlette.status import HTTP_403_FORBIDDEN
from typing import Sequence
from . import service, model
from routes.projects import application as project_app, service as project_service


async def get_errors(
        conn: AsyncSession, userid: int, limit: int, offset: int, sort: str
) -> Sequence[model.Errorlog]:
    perms = await project_app.get_projects(conn, userid)
    project_ids = [p.id for p in perms]
    cnt = 0
    returnval = []
    while True:
        logs = await service.get_errors(conn, limit, offset, sort)
        if not logs:
            break
        for log in logs:
            if log.project_id in project_ids:
                returnval.append(log)
        if len(returnval) >= limit:
            break
        offset += limit
        cnt += 1
        if cnt > 5:  # Prevent infinite loop
            break
    return returnval[:limit]


async def get_errors_by_projectid(
        conn: AsyncSession,
        userid: int,
        projectid: int,
        limit: int,
        offset: int,
        sort: str,
) -> Sequence[model.Errorlog]:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    return await service.get_errors_by_projectid(conn, projectid, limit, offset, sort)


async def read_log(
        conn: AsyncSession,
        projectid: int,
        userid: int,
        logfileid: int,
        limit: int,
        offset: int,
) -> list[str]:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    logfile = await project_service.get_logfile(conn, projectid, logfileid)
    with open(logfile.file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    selected_lines = lines[offset: offset + limit]
    return selected_lines
