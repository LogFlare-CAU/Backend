from fastapi import APIRouter, Request, Depends
from common.schema import APIResponse, response_maker as r_make, StringResponse
from common.sqlsession import get_db
from . import model, schema, application, service
from .authenticate import require_moderator, require_login, get_userid

router = APIRouter(prefix="/user", tags=["user"])


@router.get(
    "/",
    response_model=schema.UserSequenceResponse,
    responses=r_make([401, 403]),
    dependencies=require_moderator,
)
async def list_users(request: Request, conn=get_db):
    """
    모든 사용자의 정보를 반환합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    401: 인증 실패<br>
    403: 권한 없음<br>
    """
    res = await service.list_users(conn)
    return APIResponse(data=[dict(user) for user in res])


@router.get("/name", response_model=schema.UserResponse, responses=r_make([401, 403]), dependencies=require_moderator)
async def get_user_by_name(request: Request, username: str, conn=get_db):
    """
    사용자 이름으로 사용자의 정보를 반환합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    401: 인증 실패<br>
    403: 권한 없음<br>
    404: 사용자를 찾을 수 없음<br>
    """
    res = await service.get_user(conn, username)
    return APIResponse(data=dict(res))


@router.get(
    "/me",
    response_model=schema.UserResponse,
    responses=r_make([401]),
    dependencies=require_login,
)
async def get_current_user(request: Request, conn=get_db):
    """
    현재 로그인한 사용자의 정보를 반환합니다.<br>
    로그인 토큰이 필요합니다.<br>
    <br>
    401: 인증 실패<br>
    """
    userid = get_userid(request)
    res = await service.get_user_byid(conn, userid)
    return APIResponse(data=dict(res))


@router.post("/auth", response_model=StringResponse, responses=r_make([401, 404]))
async def authenticate_user(
        request: Request, auth_data: schema.UserAuthParams, conn=get_db
):
    """
    사용자를 인증합니다. 만일 인증에 성공하면 해당 사용자의 토큰을 반환합니다.<br>
    토큰은 jwt 토큰입니다.<br>
    <br>
    401: 인증 실패<br>
    404: 사용자를 찾을 수 없음
    """
    res = await application.authenticate_user(conn, auth_data)
    return APIResponse(data=res)


@router.post(
    "/",
    response_model=schema.UserResponse,
    responses=r_make([403, 409]),
    dependencies=require_moderator,
)
async def create_user(
        request: Request, user_data: schema.UserCreateParams, conn=get_db
):
    """
    새로운 사용자를 생성합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음<br>
    409: 이미 존재하는 사용자<br>
    """
    res = await service.create_user(conn, user_data)
    return APIResponse(data=dict(res))


@router.post("/{useridx}/reset_password", response_model=StringResponse, responses=r_make([403, 404]),
             dependencies=require_moderator)
async def reset_user_password(
        request: Request,
        useridx: int,
        item: schema.ResetPasswordParams,
        conn=get_db,
):
    """
    사용자의 비밀번호를 초기화합니다. 초기화된 비밀번호는 "password"입니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음<br>
    404: 사용자를 찾을 수 없음<br>
    """
    await service.reset_user_password(conn, useridx, item.new_password)
    return APIResponse(data="Password has been reset to 'password'.")


@router.patch(
    "/{useridx}",
    response_model=schema.UserResponse,
    responses=r_make([403, 404, 409]),
    dependencies=require_moderator, )
async def update_user(
        request: Request,
        useridx: int,
        user_data: schema.UserUpdateParams,
        conn=get_db,
):
    """
    사용자의 정보를 수정합니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음<br>
    404: 사용자를 찾을 수 없음<br>
    409: 이미 존재하는 사용자 이름<br>
    """
    res = await service.update_user(conn, useridx, user_data)
    return APIResponse(data=dict(res))


@router.delete(
    "/{useridx}",
    response_model=schema.UserResponse,
    responses=r_make([403, 404]),
    dependencies=require_moderator,
)
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
