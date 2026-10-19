from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED

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
