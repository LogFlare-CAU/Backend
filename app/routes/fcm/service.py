from datetime import UTC, datetime
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import model, schema


async def register_fcm_token(
    conn: AsyncSession, userid: int, item: schema.FCMTokenParams
) -> model.FCMToken:
    for _ in range(2):
        result = await conn.execute(
            select(model.FCMToken).where(model.FCMToken.fcm_token == item.fcm_token)
        )
        fcm_token = result.scalars().first()
        now = datetime.now(UTC)
        if fcm_token:
            # Idempotent: refresh, and reassign if the device changed account.
            fcm_token.user_idx = userid
            fcm_token.last_delivery = now
        else:
            fcm_token = model.FCMToken(
                user_idx=userid, fcm_token=item.fcm_token, last_delivery=now
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
    await conn.commit()
    return True


async def clean_fcm_tokens(
    conn: AsyncSession, userid: int, keep: int | None = None
) -> None:
    """Keep only the 3 most recent FCM tokens for a user.

    Recency is last_delivery (idx as tiebreak); the `keep` row is never pruned.
    """
    stmt = select(model.FCMToken).where(model.FCMToken.user_idx == userid)
    result = await conn.execute(stmt)
    tokens = sorted(
        result.scalars().all(),
        key=lambda t: (t.idx == keep, t.last_delivery or datetime.min, t.idx),
        reverse=True,
    )
    if len(tokens) <= 3:
        return
    for token in tokens[3:]:
        await conn.delete(token)
    await conn.commit()


async def get_fcm_tokens(conn: AsyncSession, userid: int) -> Sequence[model.FCMToken]:
    stmt = select(model.FCMToken).where(model.FCMToken.user_idx == userid)
    result = await conn.execute(stmt)
    tokens = result.scalars().all()
    return tokens
