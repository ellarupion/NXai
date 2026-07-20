"""IngestCandidatesService — приём постов чужих source_channels в
candidate_posts. Аналог IngestService в NX, но источник апдейтов другой:
Telegram Bot API не отдаёт апдейты для канала, где бот не участник, поэтому
вызывающая сторона здесь — не бот-хендлер, а Telethon-воркер
(interfaces/telethon_workers/main.py), слушающий events.NewMessage на
каналах, назначенных его сессии (см. ARCHITECTURE.md §7 — шардинг по
core/models/telethon_session.py).

core/ по-прежнему ничего не знает про Telethon/aiogram — сюда приходят уже
нормализованные данные (см. IncomingCandidate)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import CANDIDATE_INGESTED, get_event_bus
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.source_channel import SourceChannel

logger = get_logger(__name__)


@dataclass(frozen=True)
class IncomingCandidate:
    source_channel_tg_chat_id: int
    tg_message_id: int
    text: str


class IngestCandidatesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def receive_post(self, post: IncomingCandidate) -> UUID | None:
        """Идемпотентно относительно (source_channel_id, tg_message_id) — тот же
        паттерн, что IngestService.receive_post в NX (уникальный констрейнт +
        IntegrityError retry-read), нужен здесь на случай, если и живой апдейт, и
        параллельная докачка истории одного и того же канала увидят один пост.

        Возвращает None, если канал ещё не зарегистрирован как SourceChannel
        (воркер слушает только каналы из своей БД-конфигурации, но защита от
        рассинхронизации не помешает) или неактивен."""
        source_channel = await self._get_active_source_channel(post.source_channel_tg_chat_id)
        if source_channel is None:
            logger.warning(
                "ingest_candidates.unknown_or_inactive_source",
                tg_chat_id=post.source_channel_tg_chat_id,
            )
            return None

        existing = await self._get_candidate(source_channel.id, post.tg_message_id)
        if existing is not None:
            logger.info("ingest_candidates.duplicate_ignored", candidate_id=str(existing.id))
            return existing.id

        candidate = CandidatePost(
            source_channel_id=source_channel.id,
            tg_message_id=post.tg_message_id,
            raw_text=post.text,
            first_seen_at=datetime.now(timezone.utc),
            status=CandidatePostStatus.NEW,
        )
        self.session.add(candidate)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing = await self._get_candidate(source_channel.id, post.tg_message_id)
            if existing is not None:
                logger.info("ingest_candidates.race_resolved", candidate_id=str(existing.id))
                return existing.id
            raise

        logger.info(
            "ingest_candidates.candidate_received",
            candidate_id=str(candidate.id),
            source_channel_id=str(source_channel.id),
        )
        await get_event_bus().publish(
            CANDIDATE_INGESTED,
            {"candidate_id": str(candidate.id), "source_channel_id": str(source_channel.id)},
        )
        return candidate.id

    async def _get_active_source_channel(self, tg_chat_id: int) -> SourceChannel | None:
        result = await self.session.execute(
            select(SourceChannel).where(
                SourceChannel.tg_chat_id == tg_chat_id, SourceChannel.is_active.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def _get_candidate(self, source_channel_id: UUID, tg_message_id: int) -> CandidatePost | None:
        result = await self.session.execute(
            select(CandidatePost).where(
                CandidatePost.source_channel_id == source_channel_id,
                CandidatePost.tg_message_id == tg_message_id,
            )
        )
        return result.scalar_one_or_none()
