import time

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
)

from common.enums import Permissions
from common.jwt_utils import decode_jwt
from common.logger_setup import get_logger
from common.sqlsession import _get_db

from . import service

"""
여기에서는 사용자의 토큰 검증을 하는 종속성을 정의합니다.
"""
logger = get_logger()

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="Authorization",
    bearerFormat="Bearer",
    description="사용자 인증에 쓰이는 Bearer 토큰 인증 방식입니다.",
)


async def _require_login(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    conn: AsyncSession = Depends(_get_db),
) -> dict:
    """
    raises 400 or 401 HTTPException if token is missing, invalid, or expired.
    Verifies JWT, DB presence (revocation), and loads live permission from DB.
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
        payload = decode_jwt(token)
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    db_token = await service.get_token_by_value(conn, token)
    if db_token is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if db_token.exp is not None and db_token.exp >= 0 and int(time.time()) > db_token.exp:
        await service.delete_token(conn, db_token)
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_idx = payload.get("idx")
    if user_idx is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if db_token.user_idx != user_idx:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await service.get_user_byid(conn, int(user_idx))
    request.state.user_id = user.idx
    request.state.user = user
    request.state.auth_payload = payload
    return payload


async def _require_moderator(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    conn: AsyncSession = Depends(_get_db),
) -> None:
    await _require_login(request, credentials, conn)
    user = getattr(request.state, "user", None)
    perm = int(getattr(user, "permission", 0) if user is not None else 0)
    if perm < int(Permissions.MODERATOR):
        raise HTTPException(HTTP_403_FORBIDDEN, "Insufficient permission")
    return None


require_moderator = [Depends(_require_moderator)]
require_login = [Depends(_require_login)]


def get_userid(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        return int(user_id)
    # Fallback for safety if a handler forgot require_login (still validates JWT).
    user = request.headers.get("Authorization", None)
    if not user:
        raise HTTPException(HTTP_401_UNAUTHORIZED, detail="Invalid token")
    parts = user.split(" ")
    if len(parts) != 2:
        raise HTTPException(HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        payload = decode_jwt(parts[1])
        idx = payload.get("idx")
        if idx is None:
            raise HTTPException(HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return int(idx)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(HTTP_401_UNAUTHORIZED, detail="Invalid token")
