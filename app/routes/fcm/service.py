from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, UTC
from . import model, schema


async def register_fcm_token(
    conn: AsyncSession, userid: int, item: schema.FCMTokenParams
) -> model.FCMToken:
    fcm_token = model.FCMToken(
        user_idx=userid,
        fcm_token=item.fcm_token,
        last_delivery=datetime.now(UTC),
    )
    conn.add(fcm_token)
    await conn.commit()
    await conn.refresh(fcm_token)
    await clean_fcm_tokens(conn, userid)
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


async def clean_fcm_tokens(conn: AsyncSession, userid: int) -> None:
    """Keep only the 3 most recent FCM tokens for a user."""
    stmt = (
        select(model.FCMToken)
        .where(model.FCMToken.user_idx == userid)
        .order_by(model.FCMToken.idx.desc())
    )
    result = await conn.execute(stmt)
    tokens = result.scalars().all()
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
