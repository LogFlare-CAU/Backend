import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from common.logger_setup import get_logger
from common.sqlsession import async_session
from routes.groups.model import CollectorCursor
from routes.groups.service import record_entry
from routes.logs.model import Errorlog
from routes.logs.tasks import notify_container_event, notify_error
from routes.projects.model import Project

from .docker import DockerClient
from .parse import LineAssembler

logger = get_logger()

EXCLUDED = {"aitg-discordbot", "logflare", "logflare-docker-proxy"}
EVENTS_CURSOR = "__events__"
NOTIFY_WINDOW = timedelta(seconds=60)  # 이보다 오래된 이벤트는 요약에만 쌓고 푸시하지 않는다

collector_state: dict = {"ok": False, "last_at": None, "error": None}
container_events: list[dict] = []


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _unix(naive: datetime) -> float:
    return naive.replace(tzinfo=UTC).timestamp()


async def _project_id(conn, name: str) -> int:
    # 이름이 같은 외부 등록 프로젝트(token 있음)도 그대로 쓴다 — name 이 unique 라서.
    project = (
        await conn.execute(select(Project).where(Project.name == name))
    ).scalar_one_or_none()
    if project is None:
        project = Project(name=name, token=None)
        conn.add(project)
        await conn.flush()
    return project.id


async def _cursor(conn, name: str, default: datetime) -> CollectorCursor:
    cur = await conn.get(CollectorCursor, name)
    if cur is None:
        cur = CollectorCursor(container=name, last_ts=default)
        conn.add(cur)
    return cur


async def _collect_logs(docker: DockerClient, now: datetime, c: dict) -> list[tuple[int, int]]:
    name = c["name"]
    async with async_session() as conn:
        cur = await _cursor(conn, name, _naive(now) - timedelta(hours=24))
        since = _unix(cur.last_ts + timedelta(microseconds=1))
        # since 는 Docker 쪽 필터지만 경계 오차에 대비해 커서 이하도 걸러낸다.
        lines = [
            (ts, ln) for ts, ln in await docker.logs(c["Id"], since) if _naive(ts) > cur.last_ts
        ]
        if not lines:
            return []
        asm = LineAssembler()
        entries = []
        for ts, line in lines:
            entries += asm.feed(ts, line)
        entries += asm.flush()
        pid = await _project_id(conn, name)
        new = []
        for e in entries:
            log, _group, is_new = await record_entry(conn, pid, name, e)
            if is_new:
                new.append((log.id, pid))
        cur.last_ts = max(cur.last_ts, max(_naive(ts) for ts, _ in lines))
        await conn.commit()
    return new


async def _collect_events(docker: DockerClient, now: datetime) -> None:
    async with async_session() as conn:
        cur = await _cursor(conn, EVENTS_CURSOR, _naive(now) - timedelta(hours=24))
        events = await docker.events(_unix(cur.last_ts), now.timestamp())
        for ev in events:
            attrs = ev.get("Actor", {}).get("Attributes", {})
            name = attrs.get("name", "")
            kind = ev.get("Action", "")
            if name in EXCLUDED or not name:
                continue
            if kind == "die":
                if attrs.get("exitCode", "0") == "0":
                    continue
                detail = f"exit code {attrs.get('exitCode')}"
            elif kind.startswith("health_status"):
                if not kind.endswith("unhealthy"):
                    continue
                kind, detail = "unhealthy", "health check failed"
            else:
                detail = "out of memory"
            at = datetime.fromtimestamp(ev.get("time", now.timestamp()), UTC)
            container_events.append({"container": name, "event": kind, "at": at})
            if at >= now - NOTIFY_WINDOW:
                try:
                    await notify_container_event(
                        await _project_id(conn, name), name, kind, at, detail
                    )
                except Exception:
                    logger.exception("notify_container_event failed for %s", name)
        cutoff = now - timedelta(hours=24)
        container_events[:] = [e for e in container_events if e["at"] >= cutoff]
        cur.last_ts = _naive(now)
        await conn.commit()


async def collect_once(docker: DockerClient, now: datetime) -> None:
    failed = []
    for c in await docker.list_containers():
        if c["name"] in EXCLUDED:
            continue
        try:
            new = await _collect_logs(docker, now, c)
        except Exception:
            logger.exception("collect failed for %s", c["name"])
            failed.append(c["name"])
            continue
        for error_id, pid in new:
            try:
                await notify_error(error_id, pid, True)
            except Exception:
                logger.exception("notify_error failed")
    await _collect_events(docker, now)
    if failed:
        raise RuntimeError(f"collect failed: {', '.join(failed)}")


async def purge_old(conn, cutoff: datetime) -> None:
    """errorlogs 만 지우고 묶음은 남긴다. commit 은 호출자."""
    await conn.execute(delete(Errorlog).where(Errorlog.timestamp < _naive(cutoff)))


async def run_collector(docker: DockerClient, interval: float = 5.0) -> None:
    last_purge: datetime | None = None
    while True:
        now = datetime.now(UTC)
        try:
            await collect_once(docker, now)
            collector_state.update(ok=True, last_at=now, error=None)
        except Exception as exc:
            logger.exception("collector cycle failed")
            collector_state.update(ok=False, error=str(exc))
        try:
            if last_purge is None or now - last_purge >= timedelta(days=1):
                async with async_session() as conn:
                    await purge_old(conn, now - timedelta(days=30))
                    await conn.commit()
                last_purge = now
        except Exception:
            logger.exception("purge failed")
        await asyncio.sleep(interval)
