"""Ключевая для оператора страница панели (см. ARCHITECTURE.md §2: "в панели
можно распределять какой канал к какому боту относится") — список чужих
source_channels, добавление нового по @username/ссылке (резолв+join через одну
из Telethon-сессий пула, core/services/source_channel_lookup.py) и назначение
темы/ingest-сессии уже существующим записям."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.services.effective_settings import get_effective_settings
from core.services.source_channel_lookup import SourceChannelLookupError, resolve_and_join
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
    ingest_session_id: UUID | None
    is_active: bool
    trust_score: float

    model_config = {"from_attributes": True}


class AssignThemePayload(BaseModel):
    theme_id: UUID | None


class AssignIngestSessionPayload(BaseModel):
    ingest_session_id: UUID | None


class SourceChannelCreate(BaseModel):
    username_or_link: str
    ingest_session_id: UUID
    theme_id: UUID | None = None


@router.get("", response_model=list[SourceChannelOut])
async def list_source_channels(
    unassigned_only: bool = False, session: AsyncSession = Depends(get_db)
) -> list[SourceChannel]:
    stmt = select(SourceChannel).order_by(SourceChannel.title)
    if unassigned_only:
        stmt = stmt.where(SourceChannel.theme_id.is_(None))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=SourceChannelOut)
async def create_source_channel(
    payload: SourceChannelCreate, session: AsyncSession = Depends(get_db)
) -> SourceChannel:
    telethon_session = await session.get(TelethonSession, payload.ingest_session_id)
    if telethon_session is None:
        raise HTTPException(status_code=404, detail="TelethonSession not found")

    settings = await get_effective_settings(session)
    try:
        tg_chat_id, title, tg_username = await resolve_and_join(
            telethon_session.session_string, settings, payload.username_or_link
        )
    except SourceChannelLookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_channel = SourceChannel(
        tg_username=tg_username,
        tg_chat_id=tg_chat_id,
        title=title,
        theme_id=payload.theme_id,
        ingest_session_id=payload.ingest_session_id,
    )
    session.add(source_channel)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Канал уже добавлен") from exc
    await session.commit()
    return source_channel


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


@router.put("/{source_channel_id}/ingest-session", response_model=SourceChannelOut)
async def assign_ingest_session(
    source_channel_id: UUID, payload: AssignIngestSessionPayload, session: AsyncSession = Depends(get_db)
) -> SourceChannel:
    source_channel = await session.get(SourceChannel, source_channel_id)
    if source_channel is None:
        raise HTTPException(status_code=404, detail="SourceChannel not found")

    source_channel.ingest_session_id = payload.ingest_session_id
    await session.flush()
    await session.commit()
    return source_channel
