from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from common.schema import (
    APIResponse,
    StringSequenceResponse,
)
from common.schema import (
    response_maker as rm,
)
from common.sqlsession import get_db
from routes.projects.authenticate import get_project_id, require_project_auth
from routes.user.authenticate import get_userid, require_login

from . import application, schema, service, tasks

router = APIRouter(prefix="/log", tags=["log"])


@router.get("/", response_model=APIResponse)
async def health_check():
    return APIResponse(data={"status": "ok"})


@router.get(
    "/{project_id}/{logfileid}",
    dependencies=require_login,
    summary="로그 파일 조회",
    responses=rm([401, 403, 404]),
    response_model=StringSequenceResponse,
)
async def read_log(
        request: Request,
        project_id: int,
        logfileid: int,
        limit: int = 50,
        offset: int = 0,
        sortby: str = "newest",
        conn=get_db,
):
    """ """
    userid = get_userid(request)
    res = await application.read_log(conn, project_id, userid, logfileid, limit, offset, sortby)
    return StringSequenceResponse(data=res)


@router.post(
    "/error",
    status_code=204,
    summary="에러 추가",
    dependencies=require_project_auth,
    responses=rm([401, 403, 404]),
)
async def log_error(
        request: Request,
        log: schema.ErrorParams,
        bg_tasks: BackgroundTasks,
        conn=get_db,
):
    """
    타 코드에서 발생한 에러 로그를 수신하는 엔드포인트<br>
    <br>
    401: 인증 실패<br>
    403: 권한 없음<br>
    404: 프로젝트 없음<br>
    204: 로그 수신 성공
    """
    if log.test:
        return Response(status_code=204)
    projectid = get_project_id(request)
    error = await service.log_error(conn, projectid, log)
    bg_tasks.add_task(tasks.notify_error, error_id=error.id, projectid=projectid)
    return Response(status_code=204)


@router.get(
    "/error",
    dependencies=require_login,
    summary="에러 로그 조회",
    response_model=schema.ErrorSequenceResponse,
    responses=rm([401, 403, 404]),
)
async def get_errors(
        request: Request,
        project_id: int = None,
        limit: int = 50,
        offset: int = 0,
        sortby: str = "newest",
        conn=get_db,
):
    """
    에러 로그를 조회하는 엔드포인트<br>
    <br>
    proejct_id: 프로젝트 ID<br>
    limit: 조회할 로그 수<br>
    offset: 조회 시작 위치<br>
    <br>
    401: 인증 실패<br>
    403: 권한 없음<br>
    404: 프로젝트 없음<br>
    """
    userid = get_userid(request)
    if project_id:
        logs = await application.get_errors_by_projectid(
            conn, userid, project_id, limit, offset, sortby
        )
    else:
        logs = await application.get_errors(conn, userid, limit, offset, sortby)
    return APIResponse(data=[dict(log) for log in logs])
