from datetime import UTC, datetime, timedelta
from functools import partial

from sqlalchemy import select

from common.fcm import send_fcm_message
from common.logger_setup import get_logger
from common.sqlsession import async_session
from routes.fcm import service as fcm_service
from routes.groups.model import ErrorGroup
from routes.projects import service as project_service

from . import model

logger = get_logger()

_MAX_MSG = 1000  # FCM data 는 4096 바이트 제한 — 트레이스백 전체를 싣지 않는다


async def _send_to_recipients(conn, projectid: int, title: str, msg: str, data: dict):
    """superuser(id 1) 와 view 권한 있는 프로젝트 사용자에게 보낸다."""
    project = await project_service.get_project(conn, projectid, True)
    recipients = [1] + [u.user_id for u in project.users if u.user_id != 1 and u.view]
    for user_id in recipients:
        for fcm in await fcm_service.get_fcm_tokens(conn, user_id):
            await send_fcm_message(
                fcm.fcm_token,
                title,
                msg,
                data,
                onfailure=partial(fcm_service.remove_fcm_token, conn, fcm.fcm_token),
            )
    return project


async def notify_error(error_id: int, projectid: int, is_new: bool, test: bool = False):
    """Run after the request commits; opens a fresh DB session."""
    if not is_new:
        return
    async with async_session() as conn:
        try:
            error = await conn.get(model.Errorlog, error_id)
            if error is None:
                logger.warning("notify_error: error id %s not found", error_id)
                return
            if error.level == "WARNING":
                return
            group = (
                await conn.execute(
                    select(ErrorGroup).where(ErrorGroup.fingerprint == error.fingerprint)
                )
            ).scalar_one_or_none()
            if group is not None and group.ignored:
                return
            project = await project_service.get_project(conn, projectid, True)
            text = error.message[:_MAX_MSG]
            msg = (
                f"Error ID: {error.id}\nMessage: {text}\n"
                f"Time: {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            data = {
                "errorid": str(error.id),
                "type": error.errortype or "Unknown",
                "level": error.level,
                "timestamp": error.timestamp.isoformat(),
                "message": text,
                "projectid": str(projectid),
                "test": "true" if test else "false",
            }
            await _send_to_recipients(
                conn, projectid, f"Error in project {project.name}", msg, data
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("notify_error failed for error_id=%s", error_id)
            raise


# ponytail: 프로세스 메모리 쿨다운, 재시작하면 초기화 — 프로세스 1개라 충분
_last_event_push: dict[tuple[str, str], datetime] = {}
_COOLDOWN = timedelta(minutes=10)


async def notify_container_event(
    project_id: int, container: str, event: str, at: datetime, detail: str
) -> bool:
    """컨테이너 장애(die/oom/unhealthy) 푸시. 쿨다운 중이면 False."""
    key = (container, event)
    last = _last_event_push.get(key)
    if last is not None and at - last < _COOLDOWN:
        return False
    _last_event_push[key] = at
    message = f"{container} {event}: {detail}"
    data = {
        "errorid": "0",
        "type": f"container.{event}",
        "level": "CRITICAL",
        "timestamp": (at.astimezone(UTC).replace(tzinfo=None) if at.tzinfo else at).isoformat(),
        "message": message,
        "projectid": str(project_id),
        "test": "false",
    }
    async with async_session() as conn:
        try:
            project = await project_service.get_project(conn, project_id, True)
            await _send_to_recipients(
                conn, project_id, f"Container {event} in {project.name}", message, data
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return True
