from fastapi import APIRouter, Request
from common.sqlsession import get_db
from common.schema import response_maker as rm, APIResponse, StringResponse
from routes.user.authenticate import require_moderator, require_login, get_userid
from common.jwt_utils import decode_jwt
from . import schema, service, application

from routes.projects.model import Project

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
    response_model=StringResponse,
)
async def create_project(
    request: Request, items: schema.ProjectCreateParams, conn=get_db
) -> APIResponse:
    """
    새로운  프로젝트를 생성합니다. 프로젝트 생성에 성공하면 프로젝트 토큰을 반환합니다.
    """
    project = await service.create_project(conn, items)
    return APIResponse(data=project.token)


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
