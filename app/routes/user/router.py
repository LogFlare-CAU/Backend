from fastapi import APIRouter, Request

from common.schema import APIResponse, StringResponse
from common.schema import response_maker as r_make
from common.sqlsession import get_db

from . import application, schema, service
from .authenticate import get_token_idx, get_userid, require_login, require_moderator

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


@router.post("/auth", response_model=StringResponse, responses=r_make([401, 404, 429]))
async def authenticate_user(
        request: Request, auth_data: schema.UserAuthParams, conn=get_db
):
    """
    사용자를 인증합니다. 만일 인증에 성공하면 해당 사용자의 토큰을 반환합니다.<br>
    토큰은 jwt 토큰입니다.<br>
    <br>
    401: 인증 실패<br>
    404: 사용자를 찾을 수 없음<br>
    429: 로그인 시도 횟수 초과<br>
    """
    client_ip = request.client.host if request.client else "unknown"
    res = await application.authenticate_user(conn, auth_data, client_ip)
    return APIResponse(data=res)


@router.post(
    "/logout",
    response_model=APIResponse[schema.LogoutResult],
    responses=r_make([401]),
    dependencies=require_login,
)
async def logout(
        request: Request, item: schema.LogoutParams | None = None, conn=get_db
):
    """
    현재 로그인 토큰을 삭제하고, 그 로그인에 묶인 FCM 토큰도 함께 삭제합니다.<br>
    body 의 fcm_token(옵션)이 본인 소유면 그 행도 삭제합니다 (fcm_removed).<br>
    이미 로그아웃된 토큰으로 다시 호출하면 인증 단계에서 401 이 반환됩니다.<br>
    <br>
    401: 인증 실패 (이미 로그아웃·만료된 토큰 포함)<br>
    """
    removed = await service.logout(
        conn,
        get_userid(request),
        get_token_idx(request),
        item.fcm_token if item else None,
    )
    return APIResponse(data=schema.LogoutResult(logged_out=True, fcm_removed=removed))


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
    service.assert_can_assign_permission(request.state.user, user_data.permission)
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
    사용자의 비밀번호를 지정한 값으로 재설정합니다.<br>
    해당 사용자의 모든 로그인 토큰과 그에 묶인 FCM 토큰이 삭제됩니다.<br>
    본인 비밀번호를 재설정하면 현재 로그인은 유지됩니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음<br>
    404: 사용자를 찾을 수 없음<br>
    """
    target = await service.get_user_byid(conn, useridx)  # 404 first
    service.assert_can_manage(request.state.user, target, allow_self=True)
    own = get_userid(request) == useridx
    await service.reset_user_password(
        conn, useridx, item.new_password, current_token_idx=get_token_idx(request) if own else None
    )
    return APIResponse(data="Password has been reset.")


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
    비밀번호를 바꾸면 해당 사용자의 다른 로그인 토큰(과 묶인 FCM 토큰)이 삭제됩니다.
    이 요청을 보낸 로그인은 유지됩니다.<br>
    로그인 토큰이 필요하며, 관리자 권한이 있어야 합니다.<br>
    <br>
    403: 권한 없음 (자신보다 같거나 높은 등급 대상, 자신의 권한 변경, 자신보다 높거나 100 이상의 권한 부여)<br>
    404: 사용자를 찾을 수 없음<br>
    409: 이미 존재하는 사용자 이름<br>
    """
    await service.guard_update(conn, request.state.user, useridx, user_data)
    res = await service.update_user(
        conn, useridx, user_data, current_token_idx=get_token_idx(request)
    )
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
    target = await service.get_user_byid(conn, useridx)  # 404 first
    service.assert_can_manage(request.state.user, target)
    res = await service.delete_user(conn, useridx)
    return APIResponse(data=dict(res))
