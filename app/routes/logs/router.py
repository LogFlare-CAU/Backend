from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from common.sqlsession import get_db
from common.schema import response_maker as rm, APIResponse
from routes.projects.authenticate import require_project_auth, get_project_id
from routes.user.authenticate import require_login, get_userid
from . import schema, application, service, backgroundtasks

router = APIRouter(prefix="/log", tags=["log"])


@router.get("/")
async def health_check():
    return {"status": "ok"}


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
    projectid = get_project_id(request)
    error = await service.log_error(conn, projectid, log)
    bg_tasks.add_task(tasks.notify_error, error=error)
    return Response()


@router.get(
    "/error",
    dependencies=require_login,
    summary="에러 로그 조회",
    response_model=schema.ErrorSequenceResponse,
    responses=rm([401, 403, 404]),
)
async def get_errors(
    request: Request,
    project_id: int,
    limit: int = 50,
    offset: int = 0,
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
    logs = await application.get_errors(conn, userid, project_id, limit, offset)
    return APIResponse(data=[dict(log) for log in logs])
