import time
from datetime import UTC, datetime, timedelta
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from routes.user.model import Token

from . import model, schema

# 로그인 토큰에 묶이지 않은(token_idx NULL) 레거시 행의 유효 기간.
LEGACY_TTL = timedelta(days=30)
# 사용자별 FCM 토큰(=기기) 최대 개수. 로그인 토큰 개수 제한과 같다.
MAX_FCM_TOKENS_PER_USER = 10


def _legacy_cutoff() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - LEGACY_TTL


async def register_fcm_token(
    conn: AsyncSession,
    userid: int,
    item: schema.FCMTokenParams,
    token_idx: int | None = None,
) -> model.FCMToken:
    for _ in range(2):
        result = await conn.execute(
            select(model.FCMToken).where(model.FCMToken.fcm_token == item.fcm_token)
        )
        fcm_token = result.scalars().first()
        now = datetime.now(UTC)
        if fcm_token:
            # Idempotent: refresh, and rebind if the device changed account/login.
            fcm_token.user_idx = userid
            fcm_token.token_idx = token_idx
            fcm_token.last_delivery = now
        else:
            fcm_token = model.FCMToken(
                user_idx=userid,
                fcm_token=item.fcm_token,
                last_delivery=now,
                token_idx=token_idx,
            )
            conn.add(fcm_token)
        try:
            await conn.commit()
            break
        except IntegrityError:
            # A concurrent first registration won the insert; retry as update.
            await conn.rollback()
    else:
        raise HTTPException(status_code=409, detail="FCM token conflict")
    await conn.refresh(fcm_token)
    await clean_fcm_tokens(conn, userid, keep=fcm_token.idx)
    return fcm_token


async def remove_fcm_token(conn: AsyncSession, fcm_token: str) -> None:
    stmt = select(model.FCMToken).where(
        model.FCMToken.fcm_token == fcm_token,
    )
    result = await conn.execute(stmt)
    token = result.scalars().first()
    if token:
        await conn.delete(token)
        await conn.commit()


async def remove_user_fcm_token(
    conn: AsyncSession, userid: int, fcm_token: str
) -> bool:
    """Delete the token only if it belongs to the user. Returns whether removed."""
    removed = await delete_user_fcm_token(conn, userid, fcm_token)
    if removed:
        await conn.commit()
    return removed


async def delete_user_fcm_token(
    conn: AsyncSession, userid: int, fcm_token: str
) -> bool:
    """remove_user_fcm_token without the commit (caller commits)."""
    result = await conn.execute(
        select(model.FCMToken).where(
            model.FCMToken.fcm_token == fcm_token,
            model.FCMToken.user_idx == userid,
        )
    )
    token = result.scalars().first()
    if not token:
        return False
    await conn.delete(token)
    return True


async def delete_all_user_rows(conn: AsyncSession, userid: int) -> None:
    """Delete every FCM row of a user, bound or not (caller commits)."""
    await conn.execute(delete(model.FCMToken).where(model.FCMToken.user_idx == userid))


async def delete_for_login_tokens(conn: AsyncSession, token_idxs: Sequence[int]) -> None:
    """Delete FCM rows bound to these login tokens (caller commits)."""
    if not token_idxs:
        return
    await conn.execute(
        delete(model.FCMToken).where(model.FCMToken.token_idx.in_(list(token_idxs)))
    )


async def clean_fcm_tokens(
    conn: AsyncSession, userid: int, keep: int | None = None
) -> None:
    """Keep only the MAX_FCM_TOKENS_PER_USER most recent FCM tokens for a user.

    Recency is last_delivery (idx as tiebreak); the `keep` row is never pruned.
    """
    stmt = select(model.FCMToken).where(model.FCMToken.user_idx == userid)
    result = await conn.execute(stmt)
    tokens = sorted(
        result.scalars().all(),
        key=lambda t: (t.idx == keep, t.last_delivery or datetime.min, t.idx),
        reverse=True,
    )
    if len(tokens) <= MAX_FCM_TOKENS_PER_USER:
        return
    for token in tokens[MAX_FCM_TOKENS_PER_USER:]:
        await conn.delete(token)
    await conn.commit()


async def get_fcm_tokens(conn: AsyncSession, userid: int) -> Sequence[model.FCMToken]:
    """Deliverable FCM rows for a user.

    Bound rows: only while their login token exists and is not expired (same rule
    as require_login). Legacy unbound rows: only while last_delivery is within
    LEGACY_TTL.
    """
    now = int(time.time())
    fcm = model.FCMToken
    stmt = (
        select(fcm)
        .outerjoin(Token, Token.idx == fcm.token_idx)
        .where(fcm.user_idx == userid)
        .where(
            or_(
                and_(
                    Token.idx.isnot(None),
                    Token.user_idx == fcm.user_idx,
                    or_(Token.exp.is_(None), Token.exp < 0, Token.exp >= now),
                ),
                and_(fcm.token_idx.is_(None), fcm.last_delivery >= _legacy_cutoff()),
            )
        )
    )
    result = await conn.execute(stmt)
    return result.scalars().all()


async def sweep_stale_legacy_tokens(conn: AsyncSession) -> None:
    """Delete unbound rows not refreshed within LEGACY_TTL (caller commits)."""
    fcm = model.FCMToken
    await conn.execute(
        delete(fcm)
        .where(fcm.token_idx.is_(None))
        .where(or_(fcm.last_delivery.is_(None), fcm.last_delivery < _legacy_cutoff()))
    )
