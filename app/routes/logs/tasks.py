from functools import partial

from common.fcm import send_fcm_message
from common.logger_setup import get_logger
from common.sqlsession import async_session
from routes.fcm import service as fcm_service
from routes.projects import service as project_service

from . import model

logger = get_logger()


async def notify_error(error_id: int, projectid: int, test: bool = False):
    """Run after the request commits; opens a fresh DB session."""
    async with async_session() as conn:
        try:
            error = await conn.get(model.Errorlog, error_id)
            if error is None:
                logger.warning("notify_error: error id %s not found", error_id)
                return
            project = await project_service.get_project(conn, projectid, True)
            super_user_fcm = await fcm_service.get_fcm_tokens(conn, 1)
            title = f"Error in project {project.name}"
            msg = (
                f"Error ID: {error.id}\nMessage: {error.message}\n"
                f"Time: {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            data = {
                "errorid": str(error.id),
                "type": error.errortype or "Unknown",
                "level": error.level,
                "timestamp": error.timestamp.isoformat(),
                "message": error.message,
                "projectid": str(projectid),
                "test": "true" if test else "false",
            }

            for fcm in super_user_fcm:
                await send_fcm_message(
                    fcm.fcm_token,
                    title,
                    msg,
                    data,
                    onfailure=partial(fcm_service.remove_fcm_token, conn, fcm.fcm_token),
                )
            for user in project.users:
                if user.user_id == 1:
                    continue
                if not user.view:
                    continue
                user_fcm = await fcm_service.get_fcm_tokens(conn, user.user_id)
                for fcm in user_fcm:
                    await send_fcm_message(
                        fcm.fcm_token,
                        title,
                        msg,
                        data,
                        onfailure=partial(
                            fcm_service.remove_fcm_token, conn, fcm.fcm_token
                        ),
                    )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("notify_error failed for error_id=%s", error_id)
            raise
