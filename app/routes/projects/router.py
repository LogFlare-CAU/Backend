from fastapi import APIRouter, Request
from common.sqlsession import get_db
from common.schema import response_maker as rm, APIResponse
from routes.user.authenticate import require_moderator, require_login
from . import schema, service, application

from routes.projects.model import Project

router = APIRouter(prefix="/project", tags=["projects"])


@router.get("/")
async def list_projects():
    return {"message": "List of projects"}


@router.post(
    "/",
    summary="새로운 프로젝트 생성",
    dependencies=require_moderator,
    responses=rm([401, 403, 409]),
    response_model=schema.ProjectResponse,
)
async def create_project(
    request: Request, items: schema.ProjectCreateParams, conn=get_db
) -> APIResponse:
    project = await service.create_project(conn, items)
    return APIResponse(data=dict(project))


@router.delete(
    "/{project_id}",
    summary="프로젝트 삭제",
    dependencies=require_moderator,
    responses=rm([401, 403, 404]),
    response_model=schema.ProjectResponse,
)
async def delete_project(request: Request, project_id: int, conn=get_db) -> APIResponse:
    await service.delete_project(conn, project_id)
    return APIResponse()


@router.post("/{project_id}/logfile")
async def add_logfile(
    request: Request, project_id: int, item: schema.LogFileCreateParams, conn=get_db
):
    res = await application.add_logfile(conn, project_id, item)
    return APIResponse(data=dict(res))
