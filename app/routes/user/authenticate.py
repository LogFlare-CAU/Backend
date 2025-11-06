import logging
import time
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_400_BAD_REQUEST,
)
from common.enums import Permissions
from common.jwt_utils import decode_jwt
from . import service

"""
여기에서는 사용자의 토큰 검증을 하는 종속성을 정의합니다.
"""
logger = logging.getLogger("logflare")

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="Authorization",
    bearerFormat="Bearer",
    description="Bearer 토큰 인증 방식입니다.",
)


async def _require_moderator(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> None:
    payload = await _require_login(credentials)
    perm = int(payload.get("perm", 0))
    logger.info(f"User permission: {perm}")
    if perm < int(Permissions.MODERATOR):
        raise HTTPException(HTTP_403_FORBIDDEN, "Insufficient permission")
    return None


async def _require_login(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """
    raises 400 or 401 HTTPException if token is missing, invalid, or expired.
    :param credentials:
    :return:
    """
    if (
        credentials is None
        or not credentials.credentials
        or credentials.scheme.lower() != "bearer"
    ):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Authorization token is missing or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_jwt(token)  # 서명/무결성 검증 포함 가정
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    # 만료 검증(라이브러리에서 처리 안될 가능성 대비)
    exp = int(payload.get("exp", 0))
    if exp and exp < int(time.time()):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def _crosscheck_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> None:
    payload = await _require_login(credentials)
    # TODO: DB 에서 토큰 크로스체크
    # 근데 어차피 JWT 라서 DB 조회가 필요할까?
    return None


require_moderator = [Depends(_require_moderator)]
require_login = [Depends(_require_login)]
