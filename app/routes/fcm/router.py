import json
from functools import partial

from fastapi import APIRouter, Request, Depends, HTTPException, status
from common.schema import response_maker as r_make, APIResponse
from common.sqlsession import get_db
from common.env_utils import getenvval
from routes.user.authenticate import require_moderator, require_login, get_userid
from . import model, schema, service
from .schema import FCMConfig
from common.fcm import send_fcm_message, FCMUnregisteredError

router = APIRouter(prefix="/fcm", tags=["fcm"])


@router.get(
    "/data",
    response_model=APIResponse[FCMConfig],
    responses=r_make([401]),
    dependencies=require_login,
)
async def get_fcm_data(
    request: Request,
):
    """
    앱에서 필요한 FCM 데이터를 리턴합니다.<br>
    FCM 관련 데이터를 가져옵니다.
    """
    val = getenvval("FCM_GOOGLE_FILE")
    return APIResponse(data=json.loads(val))


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
            onfailure=partial(service.remove_fcm_token, conn, token.fcm_token),
        )
    return APIResponse(data={"sent_to": len(fcm_tokens)})
