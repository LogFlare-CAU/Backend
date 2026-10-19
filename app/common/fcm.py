import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any, Callable

import firebase_admin
from firebase_admin import credentials, exceptions, messaging

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


# 이 토큰으로는 다시 보낼 수 없다는 뜻의 오류 — 행을 지운다.
_DEAD_TOKEN_ERRORS = (messaging.UnregisteredError, messaging.SenderIdMismatchError)
_ANDROID = messaging.AndroidConfig(priority="high", ttl=timedelta(hours=24))


def _is_dead_token(err: Exception) -> bool:
    if isinstance(err, _DEAD_TOKEN_ERRORS):
        return True
    # 잘못된 토큰 값도 INVALID_ARGUMENT 로 온다; 페이로드 오류와는 메시지로 구분한다.
    return isinstance(err, exceptions.InvalidArgumentError) and (
        "registration token" in str(err).lower()
    )


def _short(token: str) -> str:
    return f"{token[:12]}…" if len(token) > 12 else token


async def send_fcm_message(
    token: str,
    title: str,
    body: str,
    data: dict | None = None,
    onfailure: Callable[[], Coroutine[Any, Any, None]] | None = None,
):
    """Send one data-only, high-priority push. Never raises.

    The app renders the notification from `data`, so there is no notification
    block; title/body are kept in the signature for callers but not sent.
    Dead tokens (unregistered, sender mismatch, invalid registration token) call
    `onfailure` to prune the row; any other error is logged and swallowed so one
    bad token never stops delivery to the others.
    """
    message = messaging.Message(data=data or {}, android=_ANDROID, token=token)
    try:
        return await asyncio.to_thread(messaging.send, message)
    except exceptions.FirebaseError as e:
        if _is_dead_token(e):
            logger.warning("FCM token %s is dead (%s); pruning", _short(token), type(e).__name__)
            if onfailure:
                try:
                    await onfailure()
                except Exception:
                    logger.exception("FCM token prune failed for %s", _short(token))
        else:
            logger.error("FCM send to %s failed: %s: %s", _short(token), type(e).__name__, e)
    except Exception:
        logger.exception("FCM send to %s failed", _short(token))
    return None
