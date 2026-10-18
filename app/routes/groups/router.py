from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from common.schema import APIResponse
from common.schema import response_maker as rm
from common.sqlsession import get_db
from routes.user.authenticate import require_moderator

from . import application

router = APIRouter(prefix="/group", tags=["groups"], dependencies=require_moderator)


class IgnoreParams(BaseModel):
    ignored: bool


@router.get("", summary="에러 묶음 목록", response_model=APIResponse, responses=rm([401, 403]))
async def list_groups(
    project_id: int | None = None,
    include_ignored: bool = False,
    sort: Literal["new", "count"] = "new",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn=get_db,
):
    return APIResponse(
        data=await application.list_groups(conn, project_id, include_ignored, sort, limit, offset)
    )


@router.get("/{group_id}", summary="에러 묶음 상세", response_model=APIResponse, responses=rm([401, 403, 404]))
async def get_group(group_id: int, conn=get_db):
    return APIResponse(data=await application.get_group(conn, group_id))


@router.patch("/{group_id}", summary="묶음 무시 토글", response_model=APIResponse, responses=rm([401, 403, 404]))
async def patch_group(group_id: int, item: IgnoreParams, conn=get_db):
    return APIResponse(data=await application.set_ignored(conn, group_id, item.ignored))
