from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND

from common.access import AccessError, load_access_config, verify_access_jwt
from common.client_ip import get_client_ip
from common.rate_limit import check_login_rate_limit, reset_login_rate_limit
from common.security import hash_password, verify_password

from . import schema, service

# Verified against when the username doesn't exist, so an unknown user costs the
# same hashing time as a wrong password and the two can't be told apart.
_DUMMY_HASH = hash_password("logflare-unknown-user")


async def authenticate_user(conn: AsyncSession, items: schema.UserAuthParams, client_ip: str) -> str:
    rate_limit_key = f"{client_ip}:{items.username}"
    check_login_rate_limit(rate_limit_key)
    try:
        user = await service.get_user(conn, items.username)
    except HTTPException:
        verify_password(_DUMMY_HASH, items.password)
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    if not verify_password(user.password, items.password):
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    reset_login_rate_limit(rate_limit_key)
    token = await service.create_token(conn, user.idx, items.keep_logged_in)
    return token.token


async def authenticate_access(conn: AsyncSession, request: Request, keep_logged_in: bool) -> str:
    """Cloudflare Access JWT 로 로그인. 설정이 없으면 404, 그 외 실패는 모두 401."""
    cfg = load_access_config()
    if cfg is None:
        raise HTTPException(HTTP_404_NOT_FOUND)
    rate_limit_key = f"access:{get_client_ip(request)}"
    check_login_rate_limit(rate_limit_key)
    token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization")
    if not token:
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    try:
        identity = verify_access_jwt(token, cfg)
    except AccessError:
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    username = cfg.users.get(identity)
    if not username:
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    try:
        user = await service.get_user(conn, username)
    except HTTPException:
        raise HTTPException(HTTP_401_UNAUTHORIZED) from None
    reset_login_rate_limit(rate_limit_key)
    created = await service.create_token(conn, user.idx, keep_logged_in)
    return created.token
