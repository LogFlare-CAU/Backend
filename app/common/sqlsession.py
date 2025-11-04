from contextlib import asynccontextmanager
from fastapi import Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import event

# SQLite + aiosqlite 엔진 생성
engine = create_async_engine(
    "sqlite+aiosqlite:///db/mydb.sqlite", echo=False, future=True
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session = async_sessionmaker(engine, expire_on_commit=False)


async def _get_db():
    async with async_session() as session:  # 세션 생성
        try:
            yield session
            await session.commit()  # 성공하면 commit
        except SQLAlchemyError:  # DB 관련 예외 → rollback
            await session.rollback()
            raise
        except Exception:  # 일반 예외 → rollback
            await session.rollback()
            raise
        finally:
            await session.close()  # 세션 정리

get_db = Depends(_get_db)

async def drop():
    await engine.dispose()
