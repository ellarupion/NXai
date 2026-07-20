"""Аутентификация админ-панели — JWT поверх логина/пароля (core/models/admin.py).

В отличие от NX здесь нет входа через Telegram Login Widget: у NX это имело
смысл, потому что "редактор" и так пишет боту в личку — единый Telegram-
аккаунт был естественным способом входа. У NXai нет понятия "редактор"
(панель — рабочее место оператора темы/тем, а не редакции с несколькими
внешними людьми) и нет одного "главного" бота, под чей токен подписывать
Login Widget — тематических ботов много и они закреплены за темами, а не за
панелью. Поэтому вход только логин/пароль (core/services/admin.py,
scripts/create_admin.py — тот же bootstrap, что в NX)."""

import time
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.models.admin import Admin
from interfaces.api.deps import get_db

JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 дней — панель, не одноразовый доступ

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentAdmin:
    admin_id: UUID
    username: str
    is_superadmin: bool


def create_access_token(admin_id: UUID, username: str, is_superadmin: bool) -> str:
    now = int(time.time())
    claims = {
        "sub": str(admin_id),
        "username": username,
        "is_superadmin": is_superadmin,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(claims, get_settings().api_secret_key, algorithm=JWT_ALGORITHM)


def _decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().api_secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный или истёкший токен"
        ) from exc


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> CurrentAdmin:
    """FastAPI Depends для защищённых роутеров (см. interfaces/api/routers/themes.py,
    source_channels.py — router-level dependencies=[Depends(get_current_admin)]).

    Сверка с БД на каждый запрос (дешёвый lookup по PK), а не только из claims:
    JWT живёт 7 дней, и без этого удалённый/разжалованный (is_superadmin) админ
    продолжал бы иметь доступ до истечения токена — тот же принцип, что
    get_current_editor в NX."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется токен")

    claims = _decode_access_token(credentials.credentials)
    admin = await session.get(Admin, UUID(claims["sub"]))
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Админ больше не существует")

    return CurrentAdmin(admin_id=admin.id, username=admin.username, is_superadmin=admin.is_superadmin)


async def require_superadmin(current: CurrentAdmin = Depends(get_current_admin)) -> CurrentAdmin:
    if not current.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступно только суперадмину")
    return current
