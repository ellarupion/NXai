from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends(get_db) — interfaces/api вызывает core.services, core/
    никогда не импортирует interfaces/ (тот же слоистый паттерн, что в NX)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
