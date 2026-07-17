from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.env_utils import getenvval

# Default SQLite path is relative to the process CWD (normally app/).
DATABASE_URL = getenvval(
    "LOGFLARE_DATABASE_URL", "sqlite+aiosqlite:///db/mydb.sqlite"
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if str(DATABASE_URL).startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async_session = async_sessionmaker(engine, expire_on_commit=False)


async def _get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


get_db = Depends(_get_db)


async def drop():
    await engine.dispose()
