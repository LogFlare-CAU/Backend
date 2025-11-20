from .env_utils import getenvval
import firebase_admin
from firebase_admin import credentials, messaging
from common.logger_setup import get_logger

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


def send_fcm_message(token, title, body, data=None):
    """
    FCM 토큰으로 푸시 알림을 보냅니다.
    :param token: 수신자의 FCM 토큰
    :param title: 알림 제목
    :param body: 알림 본문
    :param data: 추가 데이터 (딕셔너리 형태)
    :return: 메시지 전송 결과
    """
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        token=token,
    )

    response = messaging.send(message)
    return response
