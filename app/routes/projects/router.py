from fastapi import APIRouter, Request

from common.schema import APIResponse
from common.schema import response_maker as rm
from common.sqlsession import get_db
from routes.user.authenticate import get_userid, require_login, require_moderator

from . import application, schema, service

router = APIRouter(prefix="/project", tags=["projects"])


@router.get(
    "/",
    summary="프로젝트 목록 조회",
    response_model=schema.ProjectSequenceResponse,
    dependencies=require_login,
    responses=rm([401, 403, 404]),
)
async def list_projects(request: Request, conn=get_db):
    userid = get_userid(request)
    res = await application.get_projects(conn, userid)
    return APIResponse(data=[dict(project) for project in res])


@router.post(
    "/",
    summary="새로운 프로젝트 생성",
    dependencies=require_moderator,
    responses=rm([401, 403, 409]),
    response_model=schema.ProjectResponseWithToken,
)
async def create_project(
        request: Request, items: schema.ProjectCreateParams, conn=get_db
) -> APIResponse:
    """
    새로운  프로젝트를 생성합니다. 프로젝트 생성에 성공하면 프로젝트 토큰을 반환합니다.
    """
    project = await service.create_project(conn, items)
    payload = {c.name: getattr(project, c.name) for c in project.__table__.columns}
    return APIResponse(data=payload)


@router.patch(
    "/{projectid}",
    summary="프로젝트 이름 수정",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectResponse, )
async def update_project(
        request: Request, projectid: int, item: schema.ProjectCreateParams, conn=get_db
) -> APIResponse:
    res = await service.update_project(conn, projectid, item)
    return APIResponse(data=dict(res))


@router.delete(
    "/{projectid}",
    summary="프로젝트 삭제",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectResponse,
)
async def delete_project(request: Request, projectid: int, conn=get_db) -> APIResponse:
    await service.delete_project(conn, projectid)
    return APIResponse()


@router.post(
    "/{projectid}/rotate-token",
    summary="프로젝트 API 키 재발급",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectResponseWithToken,
)
async def rotate_project_token(
        request: Request, projectid: int, conn=get_db
) -> APIResponse:
    """기존 ProjectKey를 무효화하고 새 opaque 키를 발급합니다."""
    project = await service.rotate_project_token(conn, projectid)
    payload = {c.name: getattr(project, c.name) for c in project.__table__.columns}
    return APIResponse(data=payload)


@router.post(
    "/{projectid}/logfile",
    summary="로그파일 추가",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.LogFileResponse,
)
async def add_logfile(
        request: Request, projectid: int, item: schema.LogFileCreateParams, conn=get_db
):
    res = await application.add_logfile(conn, projectid, item)
    return APIResponse(data=dict(res))


@router.delete(
    "/{projectid}/logfile/{logfileid}",
    summary="로그파일 삭제",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.LogFileResponse,
)
async def delete_logfile(request: Request, projectid: int, logfileid: int, conn=get_db):
    res = await service.delete_logfile(conn, projectid, logfileid)
    return APIResponse(data=dict(res))


@router.post(
    "/perm",
    summary="프로젝트 권한 부여",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectPermsResponse,
)
async def grant_project_perms(
        request: Request, item: schema.ProjectPermsParams, conn=get_db
):
    res = await service.grant_project_perms(conn, item)
    return APIResponse(data=dict(res))


@router.get(
    "/{projectid}/perm",
    summary="프로젝트 권한 조회",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectPermsSequenceResponse, )
async def list_project_perms(
        request: Request, projectid: int, conn=get_db
):
    res = await service.list_project_perms(conn, projectid)
    return APIResponse(data=[dict(perm) for perm in res])


@router.post(
    "/perm/batch/reset",
    summary="프로젝트 권한 일괄 재설정",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectPermsSequenceResponse,
)
async def reset_project_perms_batch(
        request: Request, item: schema.ProjectPermsBatchParams, conn=get_db
):
    """
    프로젝트에 대한 권한을  일괄 재설정합니다.<br>
    기존에 부여된 모든 권한을 제거하고, 새로운 권한 목록으로 설정합니다.
    """
    res = await service.reset_project_perms_batch(conn, item)
    return APIResponse(data=[dict(perm) for perm in res])
