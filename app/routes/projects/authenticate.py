from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from common.jwt_utils import decode_jwt

# Swagger Authorize 에 표시될 Bearer 스키마
bearer_scheme = HTTPBearer(
    auto_error=True,
    scheme_name="ProjectBearer",
    description="Bearer token for project verification",
)

# Swagger Authorize 에 표시될 Project 헤더 스키마
project_header_scheme = APIKeyHeader(
    name="Project",
    auto_error=True,
    scheme_name="ProjectHeader",
    description="Project name header",
)


async def _require_project_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    project_name: str = Security(project_header_scheme),
) -> None:
    """
    인증만 수행하고, 실패 시 HTTPException(401/403) 발생.
    성공 시 아무 것도 반환하지 않음.
    """
    token = credentials.credentials
    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    token_project = payload.get("project_name")
    if token_project != project_name:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid Project name, token pair",
        )


require_project_auth = [Security(_require_project_auth)]
