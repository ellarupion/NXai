"""Ключевая для оператора страница панели (см. ARCHITECTURE.md §2: "в панели
можно распределять какой канал к какому боту относится") — список чужих
source_channels и назначение им темы/ingest-сессии. CRUD добавления нового
source_channel по @username (резолв через Telethon в chat_id/title) —
ROADMAP.md Phase 1, здесь только чтение и назначение темы для уже
существующих записей."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.source_channel import SourceChannel
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/source-channels", tags=["source-channels"], dependencies=[Depends(get_current_admin)]
)


class SourceChannelOut(BaseModel):
    id: UUID
    tg_username: str | None
    tg_chat_id: int | None
    title: str
    theme_id: UUID | None
    is_active: bool
    trust_score: float

    model_config = {"from_attributes": True}


class AssignThemePayload(BaseModel):
    theme_id: UUID | None


@router.get("", response_model=list[SourceChannelOut])
async def list_source_channels(
    unassigned_only: bool = False, session: AsyncSession = Depends(get_db)
) -> list[SourceChannel]:
    stmt = select(SourceChannel).order_by(SourceChannel.title)
    if unassigned_only:
        stmt = stmt.where(SourceChannel.theme_id.is_(None))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.put("/{source_channel_id}/theme", response_model=SourceChannelOut)
async def assign_theme(
    source_channel_id: UUID, payload: AssignThemePayload, session: AsyncSession = Depends(get_db)
) -> SourceChannel:
    source_channel = await session.get(SourceChannel, source_channel_id)
    if source_channel is None:
        raise HTTPException(status_code=404, detail="SourceChannel not found")

    source_channel.theme_id = payload.theme_id
    await session.flush()
    await session.commit()
    return source_channel
