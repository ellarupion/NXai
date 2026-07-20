"""CRUD тем — минимальный набор для Phase 0. Полный набор (привязка
target_channel/channel_bot к теме через панель, а не миграцией/скриптом,
редактирование style_prompt/cadence) — ROADMAP.md Phase 1/3."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.theme import Theme
from interfaces.api.deps import get_db

router = APIRouter(prefix="/themes", tags=["themes"])


class ThemeOut(BaseModel):
    id: UUID
    name: str
    default_style_prompt: str
    is_active: bool

    model_config = {"from_attributes": True}


class ThemeCreate(BaseModel):
    name: str
    default_style_prompt: str = ""


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
