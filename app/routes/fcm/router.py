import json

from fastapi import APIRouter, Request, Depends, HTTPException, status
from common.schema import response_maker as r_make, APIResponse
from common.sqlsession import get_db
from common.env_utils import getenvval
from routes.user.authenticate import require_moderator, require_login, get_userid
from . import model, schema, service
from .schema import FCMConfig

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
