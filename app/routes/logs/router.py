from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import Response

from common.schema import (
    APIResponse,
    StringSequenceResponse,
)
from common.schema import (
    response_maker as rm,
)
from common.sqlsession import get_db
from routes.collector.parse import Entry
from routes.groups.service import record_entry
from routes.projects.authenticate import get_project_id, require_project_auth
from routes.user.authenticate import get_userid, require_login

from . import application, schema, service, tasks
from .enum import Level, Sort

router = APIRouter(prefix="/log", tags=["log"])


@router.get("/", response_model=APIResponse)
async def health_check():
    return APIResponse(data={"status": "ok"})


@router.get(
    "/summary",
    dependencies=require_login,
    summary="로그 레벨 요약",
    response_model=schema.LogSummaryResponse,
    responses=rm([401, 403]),
)
async def get_summary(
        request: Request,
        project_id: int | None = None,
        hours: int = 24,
        conn=get_db,
):
    """
    최근 N시간(1~168, 기본 24) 레벨별 건수와 프로젝트별 에러 통계<br>
    <br>
    project_id: 지정 시 해당 프로젝트만 (접근 권한 없으면 403)
    """
    userid = get_userid(request)
    return APIResponse(data=await application.get_summary(conn, userid, project_id, hours))


@router.get(
    "/events",
    dependencies=require_login,
    summary="로그 이벤트 목록",
    response_model=schema.LogEventPageResponse,
    responses=rm([400, 401, 403]),
)
async def get_events(
        request: Request,
        project_id: int | None = None,
        min_level: Level | None = None,
        logfile_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        q: str | None = None,
        sort: Sort = Sort.NEWEST,
        grouped: bool = True,
        limit: int = Query(50, ge=1, le=200),
        cursor: str | None = None,
        conn=get_db,
):
    """
    필터/그룹핑된 로그 이벤트 목록 (커서 페이지네이션)<br>
    <br>
    grouped: (project, errortype, message) 기준 묶음 (기본 true)<br>
    q: message/errortype 대소문자 무시 부분 일치<br>
    cursor: 이전 응답의 next_cursor<br>
    <br>
    400: 잘못된 cursor, 403: 프로젝트 접근 권한 없음
    """
    userid = get_userid(request)
    filters = service.EventFilters(
        min_level=min_level, logfile_id=logfile_id, since=since, until=until,
        q=q, sort=sort, grouped=grouped,
    )
    return APIResponse(
        data=await application.list_events(
            conn, userid, project_id, filters, limit, cursor
        )
    )


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
    entry = Entry(
        level=log.level.upper(),
        errortype=log.errortype,
        message=log.message,
        ts=datetime.now(UTC),
    )
    error, _, is_new = await record_entry(conn, projectid, request.state.project.name, entry)
    await conn.commit()
    bg_tasks.add_task(
        tasks.notify_error, error_id=error.id, projectid=projectid, is_new=is_new
    )
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
