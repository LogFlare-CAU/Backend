from typing import Sequence

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST

from common.enums import Permissions
from common.logger_setup import get_logger
from common.path_utils import assert_allowed_log_path
from routes.user import service as user_service

from . import model, schema, service

logger = get_logger()


async def add_logfile(
    conn: AsyncSession, project_id: int, item: schema.LogFileCreateParams
) -> model.LogFile:
    real_path = assert_allowed_log_path(item.path, must_exist=True)
    logger.info("Adding logfile at path: %s", real_path)
    safe_item = schema.LogFileCreateParams(name=item.name, path=real_path)
    return await service.add_logfile(conn, project_id, safe_item)


async def get_projects(conn: AsyncSession, userid: int) -> Sequence[model.Project]:
    user = await user_service.get_user_byid(conn, userid)
    if user is None:
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="user not found")
    if user.permission >= Permissions.ADMINISTRATOR:
        return await service.list_projects(conn, True)
    perms = await service.get_project_perms(conn, userid)
    project_ids = [perm.project_id for perm in perms]
    returnval = []
    for project_id in project_ids:
        project = await service.get_project(conn, project_id, load=True)
        if project:
            returnval.append(project)
    return returnval
