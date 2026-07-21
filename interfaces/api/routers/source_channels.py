"""Ключевая для оператора страница панели (см. ARCHITECTURE.md §2: "в панели
можно распределять какой канал к какому боту относится") — список чужих
source_channels, добавление нового по @username/ссылке (резолв+join через одну
из Telethon-сессий пула, core/services/source_channel_lookup.py) и назначение
темы/ingest-сессии уже существующим записям."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
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
    last_scanned_at: datetime | None
    candidate_count: int

    model_config = {"from_attributes": True}

    @staticmethod
    def from_row(channel: SourceChannel, candidate_count: int) -> "SourceChannelOut":
        return SourceChannelOut(
            id=channel.id,
            tg_username=channel.tg_username,
            tg_chat_id=channel.tg_chat_id,
            title=channel.title,
            theme_id=channel.theme_id,
            ingest_session_id=channel.ingest_session_id,
            is_active=channel.is_active,
            trust_score=channel.trust_score,
            last_scanned_at=channel.last_scanned_at,
            candidate_count=candidate_count,
        )


class AssignThemePayload(BaseModel):
    theme_id: UUID | None


class AssignIngestSessionPayload(BaseModel):
    ingest_session_id: UUID | None


class SetActivePayload(BaseModel):
    is_active: bool


class SourceChannelCreate(BaseModel):
    username_or_link: str
    ingest_session_id: UUID
    theme_id: UUID | None = None


async def _candidate_count(session: AsyncSession, source_channel_id: UUID) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(CandidatePost)
        .where(CandidatePost.source_channel_id == source_channel_id)
    ) or 0


@router.get("", response_model=list[SourceChannelOut])
async def list_source_channels(
    unassigned_only: bool = False, session: AsyncSession = Depends(get_db)
) -> list[SourceChannelOut]:
    # Число кандидатов на источник одним GROUP BY, а не N+1 запросами — при
    # росте списка источников это заметно (аудит, п.4.3: показать выхлоп).
    count_col = func.count(CandidatePost.id)
    stmt = (
        select(SourceChannel, count_col)
        .outerjoin(CandidatePost, CandidatePost.source_channel_id == SourceChannel.id)
        .group_by(SourceChannel.id)
        .order_by(SourceChannel.title)
    )
    if unassigned_only:
        stmt = stmt.where(SourceChannel.theme_id.is_(None))
    result = await session.execute(stmt)
    return [SourceChannelOut.from_row(channel, count) for channel, count in result.all()]


@router.post("", response_model=SourceChannelOut)
async def create_source_channel(
    payload: SourceChannelCreate, session: AsyncSession = Depends(get_db)
) -> SourceChannelOut:
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
    return SourceChannelOut.from_row(source_channel, 0)


async def _get_or_404(session: AsyncSession, source_channel_id: UUID) -> SourceChannel:
    source_channel = await session.get(SourceChannel, source_channel_id)
    if source_channel is None:
        raise HTTPException(status_code=404, detail="SourceChannel not found")
    return source_channel


@router.put("/{source_channel_id}/theme", response_model=SourceChannelOut)
async def assign_theme(
    source_channel_id: UUID, payload: AssignThemePayload, session: AsyncSession = Depends(get_db)
) -> SourceChannelOut:
    source_channel = await _get_or_404(session, source_channel_id)
    source_channel.theme_id = payload.theme_id
    await session.flush()
    await session.commit()
    return SourceChannelOut.from_row(source_channel, await _candidate_count(session, source_channel.id))


@router.put("/{source_channel_id}/ingest-session", response_model=SourceChannelOut)
async def assign_ingest_session(
    source_channel_id: UUID, payload: AssignIngestSessionPayload, session: AsyncSession = Depends(get_db)
) -> SourceChannelOut:
    source_channel = await _get_or_404(session, source_channel_id)
    source_channel.ingest_session_id = payload.ingest_session_id
    await session.flush()
    await session.commit()
    return SourceChannelOut.from_row(source_channel, await _candidate_count(session, source_channel.id))


@router.put("/{source_channel_id}/active", response_model=SourceChannelOut)
async def set_active(
    source_channel_id: UUID, payload: SetActivePayload, session: AsyncSession = Depends(get_db)
) -> SourceChannelOut:
    """Выключенный источник не читается ingest'ом и не докачивается (аудит,
    п.4.3) — мягкая альтернатива удалению, история кандидатов сохраняется."""
    source_channel = await _get_or_404(session, source_channel_id)
    source_channel.is_active = payload.is_active
    await session.flush()
    await session.commit()
    return SourceChannelOut.from_row(source_channel, await _candidate_count(session, source_channel.id))


@router.delete("/{source_channel_id}", status_code=204)
async def delete_source_channel(
    source_channel_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    """Полное удаление вместе с кандидатами. Для «убрать из ротации, но
    сохранить историю» используйте /active — это удаление насовсем.

    DELETE-стейтментом, а не session.delete(orm): ORM-каскад обнулял бы
    candidate_posts.source_channel_id (NOT NULL → ошибка), а нам нужен
    БД-каскад ON DELETE CASCADE, который сносит кандидатов вместе с каналом."""
    await _get_or_404(session, source_channel_id)
    await session.execute(delete(SourceChannel).where(SourceChannel.id == source_channel_id))
    await session.commit()
