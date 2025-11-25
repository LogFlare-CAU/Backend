from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, UTC
from . import model, schema


async def register_fcm_token(
    conn: AsyncSession, userid: int, item: schema.FCMTokenParams
) -> model.FCMToken:
    stmt = select(model.FCMToken).where(
        model.FCMToken.user_idx == userid,
        model.FCMToken.fcm_token == item.fcm_token,
    )
    result = await conn.execute(stmt)
    existing_token = result.scalar_one_or_none()
    if existing_token:
        return existing_token
    fcm_token = model.FCMToken(
        user_idx=userid,
        fcm_token=item.fcm_token,
        last_delivery=datetime.now(UTC),
    )
    conn.add(fcm_token)
    await conn.commit()
    await conn.refresh(fcm_token)
    return fcm_token
