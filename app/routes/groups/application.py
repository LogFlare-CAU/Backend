from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.timeutil import utc_dict
from routes.collector.parse import headline
from routes.logs.model import Errorlog
from routes.projects.model import Project

from .model import ErrorGroup


def _row(group: ErrorGroup, project_name: str) -> dict:
    return {**utc_dict(group), "project_name": project_name, "headline": headline(group.sample)}


async def list_groups(
    conn: AsyncSession, project_id: int | None, include_ignored: bool, sort: str, limit: int, offset: int
) -> list[dict]:
    q = select(ErrorGroup, Project.name).join(Project, Project.id == ErrorGroup.project_id)
    if project_id is not None:
        q = q.where(ErrorGroup.project_id == project_id)
    if not include_ignored:
        q = q.where(ErrorGroup.ignored.is_(False))
    order = ErrorGroup.count if sort == "count" else ErrorGroup.first_seen
    rows = (await conn.execute(q.order_by(order.desc(), ErrorGroup.id.desc()).limit(limit).offset(offset))).all()
    return [_row(g, name) for g, name in rows]


async def _get(conn: AsyncSession, group_id: int) -> tuple[ErrorGroup, str]:
    row = (
        await conn.execute(
            select(ErrorGroup, Project.name)
            .join(Project, Project.id == ErrorGroup.project_id)
            .where(ErrorGroup.id == group_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Group not found")
    return row


async def get_group(conn: AsyncSession, group_id: int) -> dict:
    group, name = await _get(conn, group_id)
    recent = (
        await conn.execute(
            select(Errorlog)
            .where(Errorlog.fingerprint == group.fingerprint)
            .order_by(Errorlog.timestamp.desc(), Errorlog.id.desc())
            .limit(20)
        )
    ).scalars().all()
    return {**_row(group, name), "recent": [utc_dict(r) for r in recent]}


async def set_ignored(conn: AsyncSession, group_id: int, ignored: bool) -> dict:
    group, name = await _get(conn, group_id)
    group.ignored = ignored
    await conn.commit()
    return _row(group, name)
