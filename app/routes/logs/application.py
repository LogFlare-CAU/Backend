from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from starlette.status import HTTP_403_FORBIDDEN
from typing import Sequence
import re
from . import service, model
from routes.projects import application as project_app, service as project_service

LOG_START_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \s*\|\s*\w+\s*\|"
)


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
        sort: str = "newest",
) -> list[str]:
    perms = await project_app.get_projects(conn, userid)
    if projectid not in [p.id for p in perms]:
        raise HTTPException(
            HTTP_403_FORBIDDEN, detail="You do not have access to this project"
        )
    logfile = await project_service.get_logfile(conn, projectid, logfileid)
    with open(logfile.file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    entries = group_log_entries(lines)
    if sort == "newest":
        entries = entries[::-1]
    elif sort == "oldest":
        entries = entries
    selected_entries = entries[offset: offset + limit]
    return selected_entries


def group_log_entries(lines: list[str]) -> list[str]:
    """
    줄 리스트를 '로그 엔트리' 단위로 묶어서 반환.
    각 엔트리는 여러 줄(스택트레이스 포함)을 가질 수 있고,
    항상 '타임스탬프 + LEVEL + |'로 시작하는 줄에서 새 로그가 시작된다고 가정.
    """
    entries: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if LOG_START_RE.match(line):
            if current:
                entries.append(current)
            current = [line]
        else:
            if current:
                current.append(line)
            else:
                current = [line]

    if current:
        entries.append(current)
    return ["".join(chunk) for chunk in entries]
