from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from common.sqlsession import _get_db

from . import service

# Swagger Authorize 에 표시될 ProjectKey 스키마
project_key_scheme = APIKeyHeader(
    name="ProjectKey",
    auto_error=True,
    scheme_name="ProjectKeyHeader",
    description="프로젝트 API 키 (예: 'Bearer <token>')",
)

# Swagger Authorize 에 표시될 Project 헤더 스키마
project_header_scheme = APIKeyHeader(
    name="Project",
    auto_error=True,
    scheme_name="ProjectHeader",
    description="프로젝트 이름을 담는 헤더",
)


def _strip_bearer(token: str) -> str:
    """'Bearer ' 접두사 제거"""
    if token and token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


async def _require_project_auth(
    request: Request,
    project_key: str = Security(project_key_scheme),
    project_name: str = Security(project_header_scheme),
    conn: AsyncSession = Depends(_get_db),
) -> None:
    """
    ProjectKey must match the opaque token stored on the project row,
    and Project header must equal the project name.
    """
    token = _strip_bearer(project_key)
    if not token:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    try:
        project = await service.get_project_by_token(conn, token)
    except HTTPException:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    if project.name != project_name:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid Project name, token pair",
        )

    request.state.project_id = project.id
    request.state.project = project


require_project_auth = [Security(_require_project_auth)]


def get_project_id(request: Request) -> int:
    """
    현재 요청의 프로젝트 ID를 반환.
    인증이 제대로 되어 있지 않으면 예외 발생.
    """
    project_id = getattr(request.state, "project_id", None)
    if project_id is not None:
        return int(project_id)

    raise HTTPException(
        HTTP_401_UNAUTHORIZED,
        detail="Project authentication required",
    )
