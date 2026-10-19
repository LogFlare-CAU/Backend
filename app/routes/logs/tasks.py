from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from common.fcm import send_fcm_message
from common.logger_setup import get_logger
from common.sqlsession import async_session
from routes.fcm import service as fcm_service
from routes.groups.model import ContainerEvent, ErrorGroup
from routes.projects import service as project_service

from . import model

logger = get_logger()

_MAX_MSG = 1000  # FCM data 는 4096 바이트 제한 — 트레이스백 전체를 싣지 않는다
EVENT_COOLDOWN = timedelta(minutes=10)  # 같은 컨테이너·같은 이벤트는 이 안에 한 번만 푸시


async def _send_to_recipients(conn, project, title: str, msg: str, data: dict):
    """superuser(id 1) 와 view 권한 있는 프로젝트 사용자에게 보낸다. project 는 Project 또는 id."""
    if isinstance(project, int):
        project = await project_service.get_project(conn, project, True)
    recipients = [1] + [u.user_id for u in project.users if u.user_id != 1 and u.view]
    for user_id in recipients:
        rows = await fcm_service.get_fcm_tokens(conn, user_id)
        # 프루닝 실패 시 rollback 이 ORM 객체를 만료시키므로 먼저 값을 떼어 둔다
        targets = [(r.fcm_token, fcm_service.prune_callback(conn, r)) for r in rows]
        for token, prune in targets:
            await send_fcm_message(token, title, msg, data, onfailure=prune)
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
            # 프루닝이 commit/rollback 하면 ORM 값이 만료되므로 보내기 전에 떼어 둔다
            title = f"Error in project {project.name}"
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
            await _send_to_recipients(conn, project, title, msg, data)
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("notify_error failed for error_id=%s", error_id)
            raise


async def notify_container_event(event_id: int) -> bool:
    """컨테이너 장애(die/oom/unhealthy) 푸시. 이미 보냈거나 쿨다운 중이면 False.

    쿨다운은 DB 의 pushed_at 으로 판단하므로 재시작해도 이어지고, 보내기에 성공한 뒤에만 기록한다.
    """
    async with async_session() as conn:
        try:
            ev = await conn.get(ContainerEvent, event_id)
            if ev is None or ev.pushed_at is not None or ev.project_id is None:
                return False
            recent = await conn.scalar(
                select(ContainerEvent.id)
                .where(
                    ContainerEvent.container == ev.container,
                    ContainerEvent.event == ev.event,
                    ContainerEvent.pushed_at.is_not(None),
                    ContainerEvent.at > ev.at - EVENT_COOLDOWN,
                    ContainerEvent.at < ev.at + EVENT_COOLDOWN,
                )
                .limit(1)
            )
            if recent is not None:
                return False
            project = await project_service.get_project(conn, ev.project_id, True)
            container, event, at = ev.container, ev.event, ev.at
            message = f"{container} {event}: {ev.detail}"
            data = {
                "errorid": "0",
                "type": f"container.{event}",
                "level": "CRITICAL",
                "timestamp": at.isoformat(),
                "message": message,
                "projectid": str(ev.project_id),
                "test": "false",
            }
            await _send_to_recipients(
                conn, project, f"Container {event} in {project.name}", message, data
            )
            await conn.commit()  # 프루닝 결과
            ev = await conn.get(ContainerEvent, event_id)
            ev.pushed_at = datetime.now(UTC).replace(tzinfo=None)
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return True


