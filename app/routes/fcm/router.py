from datetime import datetime
from functools import partial

from fastapi import APIRouter, HTTPException, Request, status

from common.fcm import send_fcm_message
from common.schema import APIResponse
from common.schema import response_maker as r_make
from common.sqlsession import get_db
from routes.user.authenticate import get_userid, require_login, require_moderator

from . import schema, service
from .init import get_client_fcm_config

router = APIRouter(prefix="/fcm", tags=["fcm"])


@router.get(
    "/data",
    response_model=APIResponse[schema.FCMClientConfig],
    responses=r_make([401]),
    dependencies=require_login,
)
async def get_fcm_data(
        request: Request,
):
    """
    앱에서 필요한 최소 FCM 클라이언트 설정을 반환합니다.
    """
    return APIResponse(data=schema.FCMClientConfig(**get_client_fcm_config()))


@router.post(
    "/token",
    response_model=schema.FCMTokenResponse,
    responses=r_make([401]),
    dependencies=require_login,
)
async def register_fcm_token(
        request: Request,
        fcm_data: schema.FCMTokenParams,
        conn=get_db,
):
    """
    FCM 토큰을 등록합니다.<br>
    로그인 토큰이 필요합니다.
    """
    user = get_userid(request)
    token = await service.register_fcm_token(conn, user, fcm_data)
    return APIResponse(data=dict(token))


@router.post("/test", dependencies=require_moderator)
async def test_fcm_notification(
        request: Request,
        fcm_data: schema.FCMTestParams,
        conn=get_db,
):
    """
    FCM 알림 테스트용 엔드포인트입니다.<br>
    자기 자신에게 FCM 알림을 보냅니다.<br>
    관리자 권한이 필요합니다.
    """
    userid = get_userid(request)
    data = {
        "errorid": "1234",
        "type": "TestErrortype",
        "level": "ERROR",
        "timestamp": datetime.now().isoformat(),
        "message": "This is a test message sent manually from logflare server",
        "projectid": "0",
        "test": "true",
    }

    fcm_tokens = await service.get_fcm_tokens(conn, userid)
    if not fcm_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No FCM tokens registered for this user.",
        )
    for token in fcm_tokens:
        await send_fcm_message(
            token.fcm_token,
            fcm_data.title,
            fcm_data.body,
            data,
            onfailure=partial(service.remove_fcm_token, conn, token.fcm_token),
        )
    return APIResponse(data={"sent_to": len(fcm_tokens)})
