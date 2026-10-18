from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routes.collector.parse import Entry, fingerprint, mask_secrets
from routes.logs.model import Errorlog

from .model import ErrorGroup


async def record_entry(
    conn: AsyncSession, project_id: int, source: str, entry: Entry
) -> tuple[Errorlog, ErrorGroup, bool]:
    """Errorlog 를 넣고 묶음을 만들거나 갱신한다. commit 은 호출자가 한다."""
    message = mask_secrets(entry.message)
    fp = fingerprint(source, entry.level, message)
    log = Errorlog(
        project_id=project_id,
        errortype=entry.errortype,
        message=message,
        level=entry.level,
        timestamp=entry.ts,
        fingerprint=fp,
    )
    conn.add(log)
    group = (
        await conn.execute(select(ErrorGroup).where(ErrorGroup.fingerprint == fp))
    ).scalar_one_or_none()
    is_new = group is None
    if is_new:
        group = ErrorGroup(
            fingerprint=fp,
            project_id=project_id,
            level=entry.level,
            errortype=entry.errortype,
            sample=message,
            first_seen=entry.ts,
            last_seen=entry.ts,
            count=1,
        )
        conn.add(group)
    else:
        group.count += 1
        group.last_seen = max(group.last_seen, entry.ts)
    await conn.flush()
    return log, group, is_new
