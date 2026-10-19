from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from common.fcm import send_fcm_message
from common.schema import APIResponse
from common.schema import response_maker as r_make
from common.sqlsession import get_db
from routes.user.authenticate import (
    get_token_idx,
    get_userid,
    require_login,
    require_moderator,
)

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
    로그인 토큰이 필요합니다.<br>
    행은 이 요청을 인증한 로그인 토큰에 묶이며, 다른 로그인으로 다시 등록하면 그 로그인으로 옮겨집니다.<br>
    묶인 로그인 토큰이 만료·삭제되면 이 기기로는 더 이상 푸시를 보내지 않습니다.
    """
    user = get_userid(request)
    token = await service.register_fcm_token(
        conn, user, fcm_data, token_idx=get_token_idx(request)
    )
    return APIResponse(data=dict(token))


@router.delete(
    "/token",
    response_model=APIResponse[schema.FCMTokenRemoved],
    responses=r_make([401]),
    dependencies=require_login,
)
async def unregister_fcm_token(
        request: Request,
        fcm_data: schema.FCMTokenParams,
        conn=get_db,
):
    """
    본인 소유의 FCM 토큰을 해제합니다.<br>
    다른 사용자의 토큰이거나 없으면 removed=false 를 반환합니다.
    """
    user = get_userid(request)
    removed = await service.remove_user_fcm_token(conn, user, fcm_data.fcm_token)
    return APIResponse(data={"removed": removed})


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
    targets = [(t.fcm_token, service.prune_callback(conn, t)) for t in fcm_tokens]
    for token, prune in targets:
        await send_fcm_message(token, fcm_data.title, fcm_data.body, data, onfailure=prune)
    return APIResponse(data={"sent_to": len(fcm_tokens)})
