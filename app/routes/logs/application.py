from sqlalchemy.ext.asyncio import AsyncSession

from . import service, schema


async def log_error(conn: AsyncSession, log: schema.ErrorParams) -> None:
    res = await service.log_error(conn, log)
    # TODO: push notificatoin using firebase or other service
    return
