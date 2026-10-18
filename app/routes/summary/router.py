import hmac
from pathlib import Path
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from common.env_utils import getenvval
from common.schema import APIResponse
from common.timeutil import utc_iso as _iso
from common.sqlsession import get_db
from routes.collector import collector
from routes.groups.model import ErrorGroup
from routes.logs.model import Errorlog
from routes.projects.model import Project

router = APIRouter(tags=["summary"])


def _check_token(request: Request) -> None:
    path = getenvval("LOGFLARE_READ_TOKEN_FILE", "")
    try:
        expected = Path(path).read_text(encoding="utf-8").strip() if path else ""
    except OSError:
        expected = ""
    scheme, _, given = request.headers.get("Authorization", "").partition(" ")
    given = given.strip()
    if not expected or scheme.lower() != "bearer" or not hmac.compare_digest(
        given.encode(), expected.encode()
    ):
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})


@router.get("/summary", summary="home 대시보드용 요약", response_model=APIResponse)
async def summary(request: Request, conn=get_db):
    _check_token(request)
    now = datetime.now(UTC)
    since = (now - timedelta(hours=24)).replace(tzinfo=None)  # DB 는 naive UTC
    new_groups = await conn.scalar(
        select(func.count()).select_from(ErrorGroup).where(ErrorGroup.first_seen >= since)
    )
    open_groups = await conn.scalar(
        select(func.count())
        .select_from(ErrorGroup)
        .where(ErrorGroup.ignored.is_(False), ErrorGroup.last_seen >= since)
    )
    c24 = func.count(Errorlog.id).label("c24")
    rows = (
        await conn.execute(
            select(ErrorGroup, Project.name, c24)
            .join(Project, Project.id == ErrorGroup.project_id)
            .join(Errorlog, Errorlog.fingerprint == ErrorGroup.fingerprint)
            .where(ErrorGroup.ignored.is_(False), Errorlog.timestamp >= since)
            .group_by(ErrorGroup.id, Project.name)
            .order_by(c24.desc(), ErrorGroup.id)
            .limit(5)
        )
    ).all()
    state = collector.collector_state
    last_at = state.get("last_at")
    ok = bool(state.get("ok") and last_at and now - last_at <= timedelta(seconds=60))
    return APIResponse(
        data={
            "newGroups24h": new_groups,
            "openGroups": open_groups,
            "topGroups": [
                {
                    "container": name,
                    "message": (g.sample.splitlines() or [""])[0][:120],
                    "count24h": n,
                    "lastSeen": _iso(g.last_seen),
                }
                for g, name, n in rows
            ],
            "containerEvents24h": [
                {"container": e["container"], "event": e["event"], "at": _iso(e["at"])}
                for e in collector.container_events
            ],
            "collectorOk": ok,
            "lastCollectedAt": _iso(last_at) if last_at else None,
        }
    )
