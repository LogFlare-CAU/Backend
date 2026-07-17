from collections.abc import Coroutine
from typing import Any, Callable

import firebase_admin
from firebase_admin import credentials, messaging
from firebase_admin.messaging import UnregisteredError as FCMUnregisteredError

from common.logger_setup import get_logger

from .env_utils import getenvval

logger = get_logger()


def init():
    fcm_key_file = getenvval("FCM_KEY_FILE", None)
    if fcm_key_file:
        try:
            cred = credentials.Certificate(fcm_key_file)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin 초기화 성공")
        except Exception as e:
            logger.error(f"Firebase Admin 초기화 실패: {e}")
    else:
        logger.warning(
            "FCM_KEY_FILE 환경 변수가 설정되지 않았습니다. FCM 기능이 비활성화됩니다."
        )


async def send_fcm_message(
    token: str,
    title: str,
    body: str,
    data: dict | None = None,
    onfailure: Callable[[], Coroutine[Any, Any, None]] | None = None,
):
    message = messaging.Message(
        notification=messaging.Notification(
            # title=title,
            # body=body,
        ),
        data=data or {},
        token=token,
    )

    try:
        response = messaging.send(message)
        return response

    except FCMUnregisteredError:
        logger.warning(f"Unregistered FCM token: {token}")
        if onfailure:
            await onfailure()
        return None
