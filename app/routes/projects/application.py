import logging
from typing import Any, Coroutine, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST
from routes.user import service as user_service
from fastapi import HTTPException
import os
from common.enums import Permissions
from common.logger_setup import get_logger
from . import schema, service, model

logger = get_logger()


async def add_logfile(
    conn: AsyncSession, project_id: int, item: schema.LogFileCreateParams
) -> model.LogFile:
    logpath = item.path
    logger.info(f"Adding logfile at path: {logpath}")
    if os.path.exists(logpath) and os.path.isfile(logpath):
        logfile = await service.add_logfile(conn, project_id, item)
        return logfile
    else:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Log file path does not exist or is not a file: {logpath}",
        )


async def get_projects(conn: AsyncSession, userid: int) -> Sequence[model.Project]:
    user = await user_service.get_user_byid(conn, userid)
    if user is None:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="user not found")
    if user.permission == Permissions.ADMINISTRATOR:
        return await service.list_projects(conn)
    perms = await service.get_project_perms(conn, userid)
    project_ids = [perm.project_id for perm in perms]
    returnval = []
    for project_id in project_ids:
        project = await service.get_project(conn, project_id, load=True)
        if project:
            returnval.append(project)
    return returnval
