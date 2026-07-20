from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import Settings, get_settings


def make_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = make_engine()
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def dispose_engine() -> None:
    """Закрывает пул соединений и сбрасывает кэш — нужно вызвать перед тем, как
    процесс переходит в новый event loop (тот же паттерн, что в NX
    core/db.py — реальное asyncpg-соединение привязано к своему loop'у)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Использование: `async with get_session() as session: ...`.
    В FastAPI-роутерах оборачивается в Depends (interfaces/api/deps.py)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
