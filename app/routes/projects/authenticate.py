from typing import Optional
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from common.jwt_utils import decode_jwt


# Swagger Authorize 에 표시될 ProjectKey 스키마
project_key_scheme = APIKeyHeader(
    name="ProjectKey",
    auto_error=True,
    scheme_name="ProjectKeyHeader",
    description="프로젝트 인증에 쓰이는 Bearer 토큰 (예: 'Bearer <JWT>')",
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
    project_key: str = Security(project_key_scheme),
    project_name: str = Security(project_header_scheme),
) -> None:
    """
    Authorization 없이, ProjectKey + Project 헤더만으로 인증 수행.
    성공 시 아무 것도 반환하지 않음.
    """
    token = _strip_bearer(project_key)

    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    token_project = payload.get("name")
    if token_project != project_name:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid Project name, token pair",
        )


require_project_auth = [Security(_require_project_auth)]


def get_project_id(request: Request) -> int:
    """
    현재 요청의 프로젝트 ID를 반환.
    인증이 제대로 되어 있지 않으면 예외 발생.
    """
    raw = request.headers.get("ProjectKey")
    if not raw:
        raise HTTPException(HTTP_401_UNAUTHORIZED, detail="Missing ProjectKey header")

    token = _strip_bearer(raw)
    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    project_id = payload.get("id")
    if not project_id:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )
    return project_id
