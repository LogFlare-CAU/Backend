from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED

from common.security import verify_password

from . import schema, service


async def authenticate_user(conn: AsyncSession, items: schema.UserAuthParams) -> str:
    user = await service.get_user(conn, items.username)
    if not verify_password(user.password, items.password):
        raise HTTPException(HTTP_401_UNAUTHORIZED)
    token = await service.create_token(conn, user.idx, items.keep_logged_in)
    return token.token
