import time
from datetime import UTC, datetime
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_409_CONFLICT

from common.enums import Permissions
from common.jwt_utils import generate_jwt
from common.security import hash_password

from . import model, schema


async def get_user(conn: AsyncSession, username: str) -> model.User:
    stmt = select(model.User).where(model.User.username == username)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    return user


def assert_can_assign_permission(caller: model.User, permission: int) -> None:
    """Permission set through the API must be <= caller's and never Super Admin (100)."""
    if permission >= Permissions.ADMINISTRATOR:
        raise HTTPException(HTTP_403_FORBIDDEN, "Cannot assign Super Admin permission via API")
    if permission > caller.permission:
        raise HTTPException(HTTP_403_FORBIDDEN, "Cannot assign a permission higher than your own")


def assert_can_manage(
    caller: model.User, target: model.User, *, allow_self: bool = False
) -> None:
    """Target must rank strictly below the caller (self only where allow_self)."""
    if target.idx == caller.idx:
        if allow_self:
            return
        raise HTTPException(HTTP_403_FORBIDDEN, "You cannot perform this action on your own account")
    if target.permission >= caller.permission:
        raise HTTPException(
            HTTP_403_FORBIDDEN, "Insufficient permission to manage a user of equal or higher rank"
        )


async def guard_update(
    conn: AsyncSession, caller: model.User, useridx: int, item: schema.UserUpdateParams
) -> None:
    target = await get_user_byid(conn, useridx)  # 404 first
    if target.idx == caller.idx:
        if item.permission is not None and item.permission != target.permission:
            raise HTTPException(HTTP_403_FORBIDDEN, "You cannot change your own permission")
        return
    assert_can_manage(caller, target)
    if item.permission is not None:
        assert_can_assign_permission(caller, item.permission)


async def list_users(conn: AsyncSession) -> Sequence[model.User]:
    stmt = select(model.User).order_by(model.User.idx)
    result = await conn.execute(stmt)
    users = result.scalars().all()
    return users


async def reset_user_password(
    conn: AsyncSession,
    useridx: int,
    new_password: str,
    current_token_idx: int | None = None,
) -> model.User:
    """비밀번호 재설정: 해당 사용자의 모든 로그인(과 묶인 FCM)을 끊는다.

    current_token_idx 는 본인 비밀번호를 재설정할 때만 넘긴다 — 현재 세션은 남긴다.
    """
    stmt = select(model.User).where(model.User.idx == useridx)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    user.password = hash_password(new_password)
    user.updated_at = datetime.now(UTC)
    conn.add(user)
    await revoke_user_tokens(conn, user.idx, keep_idx=current_token_idx)
    await conn.commit()
    await conn.refresh(user)
    return user


async def update_user(
    conn: AsyncSession,
    useridx: int,
    item: schema.UserUpdateParams,
    current_token_idx: int | None = None,
) -> model.User:
    """비밀번호를 바꾸면 그 사용자의 다른 로그인(과 묶인 FCM)을 끊는다.

    current_token_idx(요청을 보낸 로그인)는 남긴다 — 본인 비밀번호 변경 시 현재 세션 유지.
    """
    stmt = select(model.User).where(model.User.idx == useridx)
    result = await conn.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND)
    if item.password is not None:
        user.password = hash_password(item.password)
        await revoke_user_tokens(conn, user.idx, keep_idx=current_token_idx)
    if item.permission is not None:
        user.permission = item.permission
    if item.username is not None:
        user.username = item.username
    user.updated_at = datetime.now(UTC)
    conn.add(user)
    await conn.commit()
    await conn.refresh(user)
    return user


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
    from routes.fcm import service as fcm_service  # 순환 import 회피

    await revoke_user_tokens(conn, user.idx)
    await fcm_service.delete_all_user_rows(conn, user.idx)  # 미바인딩 레거시 행 포함
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


# Session tokens: 15 minutes; keep-logged: 30 days (always finite / revocable).
SESSION_TTL_SECONDS = 900
KEEP_LOGGED_TTL_SECONDS = 30 * 24 * 60 * 60


async def create_token(
        conn: AsyncSession, user_idx: int, keep_logged: bool = False
) -> model.Token:
    await delete_expired_tokens(conn)
    user = await get_user_byid(conn, user_idx)
    token = model.Token(user_idx=user.idx)
    ttl = KEEP_LOGGED_TTL_SECONDS if keep_logged else SESSION_TTL_SECONDS
    claims = {"idx": user.idx, "perm": user.permission}
    token.token = generate_jwt(claims, expire_seconds=ttl)
    token.exp = int(time.time()) + ttl
    conn.add(token)
    await conn.commit()
    await conn.refresh(token)
    await cleanup_tokens(conn, user.idx)
    return token


async def get_token_by_value(conn: AsyncSession, token_value: str) -> model.Token | None:
    stmt = (
        select(model.Token)
        .where(model.Token.token == token_value)
        .order_by(model.Token.idx.desc())
        .limit(1)
    )
    result = await conn.execute(stmt)
    return result.scalar_one_or_none()


async def delete_token(conn: AsyncSession, token: model.Token) -> None:
    await _delete_login_tokens(conn, [token])
    await conn.commit()


async def _delete_login_tokens(
    conn: AsyncSession, tokens: Sequence[model.Token]
) -> None:
    """Delete login tokens and the FCM rows bound to them (caller commits).

    The FK is also ON DELETE CASCADE; deleting explicitly keeps this independent
    of the SQLite foreign_keys pragma.
    """
    from routes.fcm import service as fcm_service  # 순환 import 회피

    if not tokens:
        return
    await fcm_service.delete_for_login_tokens(conn, [t.idx for t in tokens])
    for token in tokens:
        await conn.delete(token)


async def revoke_user_tokens(
    conn: AsyncSession, user_idx: int, keep_idx: int | None = None
) -> None:
    """Delete all of a user's login tokens (+ bound FCM rows) except keep_idx (caller commits)."""
    stmt = select(model.Token).where(model.Token.user_idx == user_idx)
    if keep_idx is not None:
        stmt = stmt.where(model.Token.idx != keep_idx)
    result = await conn.execute(stmt)
    await _delete_login_tokens(conn, result.scalars().all())


async def logout(
    conn: AsyncSession, user_idx: int, token_idx: int, fcm_token: str | None
) -> bool:
    """Delete the current login token and its FCM rows; optionally the caller's
    own FCM row given by value. Returns whether that extra row was removed."""
    from routes.fcm import service as fcm_service  # 순환 import 회피

    fcm_removed = False
    if fcm_token:
        fcm_removed = await fcm_service.delete_user_fcm_token(conn, user_idx, fcm_token)
    token = await conn.get(model.Token, token_idx)
    if token is not None:
        await _delete_login_tokens(conn, [token])
    await conn.commit()
    return fcm_removed


async def delete_expired_tokens(conn: AsyncSession) -> None:
    from routes.fcm import service as fcm_service  # 순환 import 회피

    await fcm_service.sweep_stale_legacy_tokens(conn)
    now = int(time.time())
    stmt = (
        select(model.Token)
        .where(model.Token.exp.isnot(None))
        .where(model.Token.exp < now)
    )
    result = await conn.execute(stmt)
    await _delete_login_tokens(conn, result.scalars().all())
    await conn.commit()


# 사용자별 로그인 토큰(=기기) 최대 개수. 넘으면 가장 오래된 것부터 삭제.
MAX_LOGIN_TOKENS_PER_USER = 10


async def cleanup_tokens(conn: AsyncSession, user_idx: int) -> None:
    """사용자별 토큰 MAX_LOGIN_TOKENS_PER_USER 개까지만 유지하고 나머지는 삭제한다."""
    stmt = (
        select(model.Token)
        .where(model.Token.user_idx == user_idx)
        .order_by(model.Token.idx.desc())
    )
    result = await conn.execute(stmt)
    tokens = result.scalars().all()
    if len(tokens) > MAX_LOGIN_TOKENS_PER_USER:
        await _delete_login_tokens(conn, tokens[MAX_LOGIN_TOKENS_PER_USER:])
        await conn.commit()
