from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routes.collector.parse import Entry, fingerprint, mask_secrets
from routes.logs.model import Errorlog

from .model import ErrorGroup


RAW_MAX_LEN = 65_536


async def record_entry(
    conn: AsyncSession,
    project_id: int,
    source: str,
    entry: Entry,
    *,
    logfile_id: int | None = None,
    raw: str | None = None,
) -> tuple[Errorlog, ErrorGroup, bool]:
    """Errorlog 를 넣고 묶음을 만들거나 갱신한다. commit 은 호출자가 한다.

    raw(원본 페이로드)도 message 처럼 비밀을 가린 뒤 RAW_MAX_LEN 자로 자른다.
    """
    message = mask_secrets(entry.message)
    if raw is not None:
        raw = mask_secrets(raw)[:RAW_MAX_LEN]
    # SQLite 는 tzinfo 를 버리므로 naive UTC 로 통일해 저장·비교한다.
    ts = entry.ts.astimezone(UTC).replace(tzinfo=None) if entry.ts.tzinfo else entry.ts
    fp = fingerprint(source, entry.level, message)
    log = Errorlog(
        project_id=project_id,
        errortype=entry.errortype,
        message=message,
        level=entry.level,
        timestamp=ts,
        fingerprint=fp,
        logfile_id=logfile_id,
        raw=raw,
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
            first_seen=ts,
            last_seen=ts,
            count=1,
        )
        conn.add(group)
    else:
        group.count += 1
        group.last_seen = max(group.last_seen, ts)
    await conn.flush()
    return log, group, is_new
