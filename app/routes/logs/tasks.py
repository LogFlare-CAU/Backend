from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession
from routes.projects import service as project_service
from routes.fcm import service as fcm_service
from common.fcm import send_fcm_message, FCMUnregisteredError
from common.logger_setup import get_logger
from . import model

logger = get_logger()


async def notify_error(conn: AsyncSession, error: model.Errorlog, projectid: int, test: bool = False):
    project = await project_service.get_project(conn, projectid, True)
    super_user_fcm = await fcm_service.get_fcm_tokens(conn, 1)
    title = f"Error in project {project.name}"
    msg = f"Error ID: {error.id}\nMessage: {error.message}\nTime: {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    data = {"errorid": str(error.id), "type": error.errortype or "Unknown", "level": error.level, "timestamp": error.timestamp.isoformat(), "message": error.message, "projectid": str(projectid), "test": "true" if test else "false"}

    for fcm in super_user_fcm:  # 슈퍼 유저는 무조건 알림
        await send_fcm_message(
            fcm.fcm_token,
            title,
            msg,
            data,
            onfailure=partial(fcm_service.remove_fcm_token, conn, fcm.fcm_token),
        )
    for user in project.users:  # 프로젝트에 속한 유저들에게만 알림
        if user.user_id == 1:  # 슈퍼 유저는 이미 알림 보냈으므로 패스
            continue
        if not user.view:  # 뷰 권한이 없는 유저는 패스
            continue
        user_fcm = await fcm_service.get_fcm_tokens(conn, user.user_id)
        for fcm in user_fcm:
            await send_fcm_message(
                fcm.fcm_token,
                title,
                msg,
                data,
                onfailure=partial(fcm_service.remove_fcm_token, conn, fcm.fcm_token),
            )
