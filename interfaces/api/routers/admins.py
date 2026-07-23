"""Управление админами панели из Настроек (только для суперадминов):
суперадмин видит и меняет всё, включая LLM/Telegram-ключи (раздел /settings
gated require_superadmin); обычный админ ведёт контент, ключей не касается.
Раньше админов можно было заводить только через scripts/create_admin.py по SSH."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.admin import Admin
from core.services.admin import (
    AdminAlreadyExistsError,
    AdminService,
    LastSuperadminError,
    PasswordTooLongError,
)
from interfaces.api.auth import CurrentAdmin, require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/admins", tags=["admins"], dependencies=[Depends(require_superadmin)])

MIN_PASSWORD_LENGTH = 8


class AdminOut(BaseModel):
    id: UUID
    username: str
    is_superadmin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminCreate(BaseModel):
    username: str
    password: str
    is_superadmin: bool = False


@router.get("", response_model=list[AdminOut])
async def list_admins(session: AsyncSession = Depends(get_db)) -> list[Admin]:
    result = await session.execute(select(Admin).order_by(Admin.created_at))
    return list(result.scalars().all())


@router.post("", response_model=AdminOut)
async def create_admin(payload: AdminCreate, session: AsyncSession = Depends(get_db)) -> Admin:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Логин не может быть пустым")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
        )
    try:
        admin = await AdminService(session).create_admin(
            username, payload.password, payload.is_superadmin
        )
    except AdminAlreadyExistsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PasswordTooLongError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return admin


@router.delete("/{admin_id}", status_code=204)
async def delete_admin(
    admin_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(require_superadmin),
) -> None:
    """Сервис сам держит два предохранителя: нельзя удалить себя и нельзя
    удалить последнего суперадмина (иначе некому будет управлять ключами)."""
    try:
        await AdminService(session).delete_admin(admin_id, current.admin_id)
    except (ValueError, LastSuperadminError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
