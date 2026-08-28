from fastapi import Request
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends(get_db) — interfaces/api вызывает core.services, core/
    никогда не импортирует interfaces/ (тот же слоистый паттерн, что в NX)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


def client_ip(request: Request) -> str | None:
    """Адрес человека, а не контейнера.

    За nginx request.client.host — это адрес самого nginx, один и тот же для всех, и
    журнал с таким адресом бесполезен. Берём X-Real-IP, который nginx ставит из
    $remote_addr (deploy/nginx/nginx.conf).

    X-Forwarded-For намеренно НЕ используем: клиент может прислать его сам, и тогда
    в журнале окажется адрес, который выбрал сам вошедший. X-Real-IP nginx
    перезаписывает всегда, подделать его снаружи нельзя."""
    header = request.headers.get("x-real-ip")
    if header:
        return header.strip()[:45]
    return request.client.host if request.client else None
