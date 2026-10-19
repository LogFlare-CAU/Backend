import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from common.logger_setup import get_logger
from common.sqlsession import async_session
from routes.groups.model import CollectorCursor, ContainerEvent
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
# 끝나지 않은 줄을 다음 폴링까지 들고 있는 시간 (NOTIFY_WINDOW 보다 짧아야 늦게 끝난 에러도 푸시된다).
TAIL_GRACE = timedelta(seconds=3)  # 예외 줄 뒤 체인, ERROR 줄 뒤 트레이스백 — 같은 write 라 곧 온다
FRAME_GRACE = timedelta(seconds=30)  # 트레이스백 프레임 중간 — 예외 줄을 기다린다
MAX_PENDING = 2000  # 이보다 길면 기다리지 않고 내보낸다

collector_state: dict = {"ok": False, "last_at": None, "error": None}


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


def _load_pending(raw: str | None) -> list[tuple[datetime, str]]:
    if not raw:
        return []
    try:
        return [(datetime.fromisoformat(ts), ln) for ts, ln in json.loads(raw)]
    except (ValueError, TypeError):
        logger.warning("collector: 보관 줄을 읽지 못해 버린다")
        return []


def _dump_pending(lines: list[tuple[datetime, str]]) -> str | None:
    return json.dumps([[ts.isoformat(), ln] for ts, ln in lines], ensure_ascii=False) if lines else None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _collect_logs(docker: DockerClient, now: datetime, c: dict) -> list[tuple[int, int]]:
    name = c["name"]
    async with async_session() as conn:
        cur = await _cursor(conn, name, _naive(now) - timedelta(hours=24))
        since = _unix(cur.last_ts + timedelta(microseconds=1))
        # since 는 Docker 쪽 필터지만 경계 오차에 대비해 커서 이하도 걸러낸다.
        lines = [
            (ts, ln) for ts, ln in await docker.logs(c["Id"], since) if _naive(ts) > cur.last_ts
        ]
        carried = _load_pending(cur.pending)
        if not lines and not carried:
            return []
        # 지난 폴링에서 끝나지 않은 줄(트레이스백 중간, 뒤를 기다리던 ERROR 줄)을 먼저 넣어 이어 붙인다.
        # 폴링 경계에서 트레이스백이 둘로 쪼개져 가짜 새 묶음이 푸시되던 문제를 막는다.
        asm = LineAssembler()
        entries = []
        for ts, line in carried + lines:
            entries += asm.feed(ts, line)
        pend = asm.pending()
        if pend:
            grace = FRAME_GRACE if asm.in_frames() else TAIL_GRACE
            if len(pend) > MAX_PENDING or _aware(now) - _aware(pend[-1][0]) >= grace:
                entries += asm.flush()
                pend = []
        cur.pending = _dump_pending(pend)
        new = []
        if entries:
            pid = await _project_id(conn, name)
            for e in entries:
                log, _group, is_new = await record_entry(conn, pid, name, e)
                # 첫 attach 의 24h 백필은 요약에만 쌓고 푸시하지 않는다.
                if is_new and _naive(e.ts) >= _naive(now) - NOTIFY_WINDOW:
                    new.append((log.id, pid))
        if lines:
            cur.last_ts = max(cur.last_ts, max(_naive(ts) for ts, _ in lines))
        await conn.commit()
    return new


def _event_kind(ev: dict) -> tuple[str, str, str] | None:
    """(컨테이너, 이벤트, 설명). 알릴 필요 없는 이벤트는 None."""
    attrs = ev.get("Actor", {}).get("Attributes", {})
    name = attrs.get("name", "")
    kind = ev.get("Action", "")
    if name in EXCLUDED or not name:
        return None
    if kind == "die":
        if attrs.get("exitCode", "0") == "0":
            return None
        return name, kind, f"exit code {attrs.get('exitCode')}"
    if kind.startswith("health_status"):
        return (name, "unhealthy", "health check failed") if kind.endswith("unhealthy") else None
    if kind == "restart":
        return name, kind, "restarted"
    if kind == "oom":
        return name, kind, "out of memory"
    return None


def _event_at(ev: dict, now: datetime) -> datetime:
    if "timeNano" in ev:
        return datetime.fromtimestamp(int(ev["timeNano"]) // 1000 / 1_000_000, UTC)
    return datetime.fromtimestamp(ev.get("time", now.timestamp()), UTC)


async def _collect_events(docker: DockerClient, now: datetime) -> None:
    pending: list[int] = []
    async with async_session() as conn:
        cur = await _cursor(conn, EVENTS_CURSOR, _naive(now) - timedelta(hours=24))
        events = await docker.events(_unix(cur.last_ts), now.timestamp())
        for ev in events:
            k = _event_kind(ev)
            if k is None:
                continue
            name, kind, detail = k
            at = _event_at(ev, now)
            # 같은 이벤트(컨테이너·종류·시각)는 한 번만 — 커서 경계에서 다시 읽혀도 두 번 푸시하지 않는다.
            exists = await conn.scalar(
                select(ContainerEvent.id).where(
                    ContainerEvent.container == name,
                    ContainerEvent.event == kind,
                    ContainerEvent.at == _naive(at),
                )
            )
            if exists is not None:
                continue
            notify = kind != "restart" and at >= now - NOTIFY_WINDOW
            row = ContainerEvent(
                container=name,
                event=kind,
                at=_naive(at),
                detail=detail,
                project_id=await _project_id(conn, name) if notify else None,
            )
            conn.add(row)
            await conn.flush()
            if notify:
                pending.append(row.id)
        cur.last_ts = _naive(now)
        await conn.commit()
    # 새 프로젝트가 commit 된 뒤에야 다른 세션에서 보인다.
    for event_id in pending:
        try:
            await notify_container_event(event_id)
        except Exception:
            logger.exception("notify_container_event failed for event %s", event_id)


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
    """errorlogs·컨테이너 이벤트만 지우고 묶음은 남긴다. commit 은 호출자."""
    await conn.execute(delete(Errorlog).where(Errorlog.timestamp < _naive(cutoff)))
    await conn.execute(delete(ContainerEvent).where(ContainerEvent.at < _naive(cutoff)))


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
