import base64
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from common.path_utils import assert_allowed_log_path
from routes.projects import application as project_app
from routes.projects import service as project_service

from . import model, schema, service

LOG_START_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \s*\|\s*\w+\s*\|"
)


async def get_errors(
        conn: AsyncSession, userid: int, limit: int, offset: int, sort: str
) -> Sequence[model.Errorlog]:
    perms = await project_app.get_projects(conn, userid)
    project_ids = [p.id for p in perms]
    return await service.get_errors_for_projects(
        conn, project_ids, limit, offset, sort
    )


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
    real_path = assert_allowed_log_path(logfile.file_path, must_exist=True)
    with open(real_path, "r", encoding="utf-8") as f:
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


async def get_summary(
        conn: AsyncSession, userid: int, project_id: int | None, hours: int
) -> schema.LogSummary:
    hours = max(1, min(hours, 168))
    accessible = [p.id for p in await project_app.get_projects(conn, userid)]
    if project_id is not None:
        if project_id not in accessible:
            raise HTTPException(
                HTTP_403_FORBIDDEN, detail="You do not have access to this project"
            )
        accessible = [project_id]
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
    return schema.LogSummary(
        window_hours=hours,
        since=since,
        counts=await service.count_levels(conn, accessible, since),
        projects=await service.project_summaries(conn, accessible, since),
    )


def encode_cursor(offset: int, ceiling: datetime) -> str:
    raw = json.dumps({"o": offset, "t": ceiling.isoformat()}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, datetime]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        offset, ceiling = data["o"], datetime.fromisoformat(data["t"])
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("bad offset")
        return offset, ceiling.replace(tzinfo=None)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(HTTP_400_BAD_REQUEST, detail="Invalid cursor") from None


async def list_events(
        conn: AsyncSession,
        userid: int,
        project_id: int | None,
        filters: service.EventFilters,
        limit: int,
        cursor: str | None,
) -> schema.LogEventPage:
    accessible = [p.id for p in await project_app.get_projects(conn, userid)]
    if project_id is not None:
        if project_id not in accessible:
            raise HTTPException(
                HTTP_403_FORBIDDEN, detail="You do not have access to this project"
            )
        accessible = [project_id]
    if cursor:
        offset, ceiling = decode_cursor(cursor)
    else:
        offset = 0
        ceiling = await service.newest_event_time(conn, accessible, filters)
    items = await service.list_events(
        conn, accessible, filters, offset, limit + 1, ceiling
    )
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        next_cursor = encode_cursor(offset + limit, ceiling)
    return schema.LogEventPage(items=items, next_cursor=next_cursor)
