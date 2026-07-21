"""CRUD тем — создание, список, получение и редактирование (переименование,
правка стиля по умолчанию, включение/выключение). Привязка target_channel/
channel_bot к теме делается на своих страницах панели."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.theme import Theme
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/themes", tags=["themes"], dependencies=[Depends(get_current_admin)])


class ThemeOut(BaseModel):
    id: UUID
    name: str
    default_style_prompt: str
    is_active: bool
    digest_enabled: bool
    digest_hour: int

    model_config = {"from_attributes": True}


class ThemeCreate(BaseModel):
    name: str
    default_style_prompt: str = ""


class ThemeUpdate(BaseModel):
    """Все поля опциональны — PUT меняет только переданное."""

    name: str | None = None
    default_style_prompt: str | None = None
    is_active: bool | None = None
    digest_enabled: bool | None = None
    digest_hour: int | None = None


@router.get("", response_model=list[ThemeOut])
async def list_themes(session: AsyncSession = Depends(get_db)) -> list[Theme]:
    result = await session.execute(select(Theme).order_by(Theme.name))
    return list(result.scalars().all())


@router.post("", response_model=ThemeOut)
async def create_theme(payload: ThemeCreate, session: AsyncSession = Depends(get_db)) -> Theme:
    theme = Theme(name=payload.name, default_style_prompt=payload.default_style_prompt)
    session.add(theme)
    await session.flush()
    await session.commit()
    return theme


@router.get("/{theme_id}", response_model=ThemeOut)
async def get_theme(theme_id: UUID, session: AsyncSession = Depends(get_db)) -> Theme:
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/{theme_id}", response_model=ThemeOut)
async def update_theme(
    theme_id: UUID, payload: ThemeUpdate, session: AsyncSession = Depends(get_db)
) -> Theme:
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Название темы не может быть пустым")
        theme.name = name
    if payload.default_style_prompt is not None:
        theme.default_style_prompt = payload.default_style_prompt
    if payload.is_active is not None:
        theme.is_active = payload.is_active
    if payload.digest_enabled is not None:
        theme.digest_enabled = payload.digest_enabled
    if payload.digest_hour is not None:
        if not 0 <= payload.digest_hour <= 23:
            raise HTTPException(status_code=400, detail="Час дайджеста должен быть от 0 до 23")
        theme.digest_hour = payload.digest_hour

    await session.flush()
    await session.commit()
    return theme
