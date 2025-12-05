import time
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_409_CONFLICT, HTTP_404_NOT_FOUND
from common.jwt_utils import generate_jwt
from common.security import hash_password
from datetime import datetime, UTC
from . import model, schema


async def get_user(conn: AsyncSession, username: str) -> model.User:
    stmt = select(model.User).where(model.User.username == username)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    return user


async def list_users(conn: AsyncSession) -> Sequence[model.User]:
    stmt = select(model.User).order_by(model.User.idx)
    result = await conn.execute(stmt)
    users = result.scalars().all()
    return users


async def create_user(conn: AsyncSession, item: schema.UserCreateParams) -> model.User:
    stmt = select(model.User).where(model.User.username == item.username)
    result = await conn.execute(stmt)
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(HTTP_409_CONFLICT)
    user = model.User(
        username=item.username,
        password=hash_password(item.password),
        permission=item.permission,
    )
    conn.add(user)
    await conn.commit()
    await conn.refresh(user)
    return user


async def delete_user(conn: AsyncSession, useridx: int) -> model.User:
    stmt = select(model.User).where(model.User.idx == useridx)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    await conn.delete(user)
    await conn.commit()
    return user


async def get_user_byid(conn: AsyncSession, useridx: int) -> model.User:
    """1번 사용자는 항상 슈퍼유저이다."""
    stmt = select(model.User).where(model.User.idx == useridx)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    return user


async def create_token(
    conn: AsyncSession, user_idx: int, keep_logged: bool = False
) -> model.Token:
    await delete_expired_tokens(conn)
    user = await get_user_byid(conn, user_idx)
    token = model.Token(user_idx=user.idx)
    json = {"idx": user.idx, "perm": user.permission}
    if keep_logged:
        json["expire_at"] = -1
    else:
        json["expire_at"] = int(time.time()) + 900  # 15 minutes
    token.token = generate_jwt(json)
    token.exp = json["expire_at"]
    conn.add(token)
    await conn.commit()
    await conn.refresh(token)
    await cleanup_tokens(conn, user.idx)
    return token


async def delete_expired_tokens(conn: AsyncSession) -> None:
    now = int(time.time())
    stmt = (
        select(model.Token)
        .where(model.Token.exp.isnot(None))
        .where(model.Token.exp < now)
        .where(model.Token.exp >= 0)
    )
    result = await conn.execute(stmt)
    expired_tokens = result.scalars().all()
    for token in expired_tokens:
        await conn.delete(token)
    await conn.commit()


async def cleanup_tokens(conn: AsyncSession, user_idx: int) -> None:
    """사용자별 토큰 3개까지만 유지하고 나머지는 삭제한다."""
    stmt = (
        select(model.Token)
        .where(model.Token.user_idx == user_idx)
        .order_by(model.Token.idx.desc())
    )
    result = await conn.execute(stmt)
    tokens = result.scalars().all()
    if len(tokens) > 3:
        for token in tokens[3:]:
            await conn.delete(token)
        await conn.commit()
