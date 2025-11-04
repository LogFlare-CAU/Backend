from fastapi import APIRouter, Request, Depends
from common.schema import APIResponse, response_maker as r_make, StringResponse
from common.authentication import require_moderator
from common.sqlsession import get_db
from . import model, schema, application, service

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/auth", response_model=StringResponse, responses=r_make([401, 404]))
async def authenticate_user(request: Request, auth_data: schema.UserAuthParams, conn=get_db):
    """
    사용자를 인증합니다. 만일 인증에 성공하면 해당 사용자의 토큰을 반환합니다.<br>
    토큰은 jwt 토큰입니다.<br>
    <br>
    401: 인증 실패<br>
    404: 사용자를 찾을 수 없음
    """
    res = await application.authenticate_user(conn, auth_data)
    return APIResponse(data=res)


@router.post("/create", response_model=schema.UserResponse, responses=r_make([403, 409]), dependencies=require_moderator)
async def create_user(request: Request, user_data: schema.UserCreateParams, conn=get_db):
    """
    새로운 사용자를 생성합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음<br>
    409: 이미 존재하는 사용자<br>
    """
    res = await service.create_user(conn, user_data)
    return APIResponse(data=dict(res))


@router.delete("/delete/{useridx}", response_model=schema.UserResponse, responses=r_make([403, 404]), dependencies=require_moderator)
async def delete_user(request: Request, useridx: int, conn=get_db):
    """
    사용자를 삭제합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음  <br>
    404: 사용자를 찾을 수 없음<br>
    """
    res = await service.delete_user(conn, useridx)
    return APIResponse(data=dict(res))
