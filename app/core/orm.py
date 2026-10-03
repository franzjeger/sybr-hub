from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Engine cache so we don't recreate it on every request,
# but can still recreate it if tests change DB_PATH.
_engines = {}


def get_engine():
    from app.core import database

    path = str(database.DB_PATH)
    if path not in _engines:
        # Use NullPool for SQLite to avoid connection persistence issues across tests,
        # or rely on SQLAlchemy default. NullPool is safest for tests.
        DATABASE_URL = f"sqlite+aiosqlite:///{path}"
        engine = create_async_engine(
            DATABASE_URL, echo=False, connect_args={"timeout": 30}, poolclass=NullPool
        )

        # SQLite defaults foreign-key enforcement to OFF per-connection, so
        # every ON DELETE CASCADE declared across the SQLModel tables would
        # otherwise be silently unenforced. aiosqlite's DBAPI connect event
        # fires synchronously even though the engine is async, so a plain
        # sync 'connect' listener on the sync engine is the correct hook here
        # (mirrors the PRAGMA applied per-connection in app/core/database.py).
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        _engines[path] = engine
    return _engines[path]


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session


async def close_orm() -> None:
    for engine in _engines.values():
        await engine.dispose()
    _engines.clear()
