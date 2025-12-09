from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from . import schema, model
from common.jwt_utils import generate_jwt

from routes.user.service import get_user


async def create_project(
        conn: AsyncSession, items: schema.ProjectCreateParams
) -> model.Project:
    project = model.Project(name=items.name)
    conn.add(project)
    await conn.commit()
    await conn.refresh(project)
    json = {"name": project.name, "id": project.id}
    token = generate_jwt(json)
    project.token = token
    await conn.commit()
    await conn.refresh(project)
    return project


async def delete_project(conn: AsyncSession, project_id: int) -> None:
    result = await conn.execute(
        select(model.Project).where(model.Project.id == project_id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await conn.delete(project)
    await conn.commit()


async def update_project(conn: AsyncSession, projectid, items: schema.ProjectCreateParams) -> model.Project:
    result = await conn.execute(
        select(model.Project).where(model.Project.id == projectid)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.name = items.name
    await conn.commit()
    await conn.refresh(project)
    return project


async def get_project(
        conn: AsyncSession, project_id: int, load: bool = False
) -> model.Project:
    stmt = select(model.Project).where(model.Project.id == project_id)
    if load:
        stmt = stmt.options(selectinload(model.Project.logfiles)).options(
            selectinload(model.Project.users)
        )
    result = await conn.execute(stmt)
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def get_project_by_token(conn: AsyncSession, token: str) -> model.Project:
    result = await conn.execute(
        select(model.Project).where(model.Project.token == token)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def get_project_by_name(conn: AsyncSession, name: str) -> model.Project:
    result = await conn.execute(select(model.Project).where(model.Project.name == name))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def add_logfile(
        conn: AsyncSession, project_id: int, item: schema.LogFileCreateParams
) -> model.LogFile:
    logfile = model.LogFile()
    logfile.project_id = project_id
    logfile.file_name = item.name
    logfile.file_path = item.path
    conn.add(logfile)
    await conn.commit()
    await conn.refresh(logfile)
    return logfile


async def delete_logfile(
        conn: AsyncSession, projectid: int, logfileid: int
) -> model.LogFile:
    stmt = select(model.LogFile).where(
        model.LogFile.id == logfileid,
        model.LogFile.project_id == projectid,
    )
    result = await conn.execute(stmt)
    logfile = result.scalars().first()
    if not logfile:
        raise HTTPException(status_code=404, detail="LogFile not found")
    await conn.delete(logfile)
    await conn.commit()
    return logfile


async def get_logfile(
        conn: AsyncSession, projectid: int, logfileid: int
) -> model.LogFile:
    stmt = select(model.LogFile).where(
        model.LogFile.id == logfileid,
        model.LogFile.project_id == projectid,
    )
    result = await conn.execute(stmt)
    logfile = result.scalars().first()
    if not logfile:
        raise HTTPException(status_code=404, detail="LogFile not found")
    return logfile


async def list_projects(
        conn: AsyncSession, load: bool = False
) -> Sequence[model.Project]:
    stmt = select(model.Project)
    if load:
        stmt = stmt.options(selectinload(model.Project.logfiles)).options(
            selectinload(model.Project.users)
        )
    result = await conn.execute(stmt)
    projects = result.scalars().all()
    return projects


async def get_project_perms(
        conn: AsyncSession, userid: int
) -> Sequence[model.ProjectPerms]:
    """
    Get project permissions for a user
    :param conn:
    :param userid:
    :return:
    """
    stmt = select(model.ProjectPerms).where(model.ProjectPerms.user_id == userid)
    result = await conn.execute(stmt)
    perms = result.scalars().all()
    return perms


async def list_project_perms(
        conn: AsyncSession, projectid: int
) -> Sequence[model.ProjectPerms]:
    """
    List project permissions for a project
    :param conn:
    :param projectid:
    :return:
    """
    stmt = select(model.ProjectPerms).where(model.ProjectPerms.project_id == projectid)
    result = await conn.execute(stmt)
    perms = result.scalars().all()
    return perms


async def grant_project_perms(
        conn: AsyncSession, item: schema.ProjectPermsParams
) -> model.ProjectPerms:
    stmt = select(model.ProjectPerms).where(
        model.ProjectPerms.user_id == item.user_id,
        model.ProjectPerms.project_id == item.project_id,
    )
    result = await conn.execute(stmt)
    perms = result.scalars().first()
    if perms:
        perms.view = True
        return perms
    perms = model.ProjectPerms(
        user_id=item.user_id, project_id=item.project_id, view=True
    )
    conn.add(perms)
    await conn.commit()
    await conn.refresh(perms)
    return perms


async def reset_project_perms_batch(
        conn: AsyncSession, item: schema.ProjectPermsBatchParams
) -> Sequence[model.ProjectPerms]:
    stmt = delete(model.ProjectPerms).where(
        model.ProjectPerms.project_id == item.projectid
    )
    await conn.execute(stmt)
    await conn.commit()
    for username in item.usernames:
        user = await get_user(conn, username)
        perms = model.ProjectPerms(
            user_id=user.idx, project_id=item.projectid, view=True
        )
        conn.add(perms)
    await conn.commit()
    stmt = select(model.ProjectPerms).where(
        model.ProjectPerms.project_id == item.projectid
    )
    result = await conn.execute(stmt)
    perms = result.scalars().all()
    return perms
