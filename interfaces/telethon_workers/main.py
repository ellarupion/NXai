"""Telethon ingest worker — точка входа для чтения чужих source_channels (см.
ARCHITECTURE.md §2, §7). Один TelegramClient на одну активную
TelethonSession, слушает только каналы, которые панель к ней приписала
(SourceChannel.ingest_session_id) — так шардинг по лимитам аккаунта
(число каналов, частота GetHistoryRequest) заложен с самого начала, а не
добавляется поверх одной раздутой сессии.

Реализовано: живой приём через events.NewMessage → IngestCandidatesService.
НЕ реализовано (см. ROADMAP.md Phase 1): докачка истории при добавлении
нового source_channel или после простоя (SourceChannel.last_scanned_message_id
+ core/statistics/client.py.SourceStatsClient.get_messages_after — тот же
принцип, что backfill в NX, здесь только место для него подготовлено)."""

import asyncio

from sqlalchemy import select
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from core.config import get_settings
from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.services.ingest_candidates import IncomingCandidate, IngestCandidatesService

logger = get_logger(__name__)


async def _source_chat_ids_for(session_id) -> list[int]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(SourceChannel.tg_chat_id).where(
                SourceChannel.ingest_session_id == session_id,
                SourceChannel.is_active.is_(True),
                SourceChannel.tg_chat_id.is_not(None),
            )
        )
        return [row[0] for row in result.all()]


async def run_session_worker(telethon_session: TelethonSession) -> None:
    settings = get_settings()
    source_chat_ids = await _source_chat_ids_for(telethon_session.id)
    if not source_chat_ids:
        logger.warning("telethon_worker.no_channels_assigned", session_label=telethon_session.label)
        return

    client = TelegramClient(
        StringSession(telethon_session.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    @client.on(events.NewMessage(chats=source_chat_ids))
    async def _on_new_message(event) -> None:  # noqa: ANN001 — telethon event type
        if not event.raw_text:
            return
        session_factory = get_session_factory()
        async with session_factory() as session:
            await IngestCandidatesService(session).receive_post(
                IncomingCandidate(
                    source_channel_tg_chat_id=event.chat_id,
                    tg_message_id=event.id,
                    text=event.raw_text,
                )
            )
            await session.commit()

    await client.start()
    logger.info(
        "telethon_worker.started", session_label=telethon_session.label, channel_count=len(source_chat_ids)
    )
    await client.run_until_disconnected()


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(TelethonSession).where(TelethonSession.is_active.is_(True)))
        telethon_sessions = list(result.scalars().all())

    if not telethon_sessions:
        logger.warning("telethon_worker.no_active_sessions")
        return

    await asyncio.gather(*(run_session_worker(ts) for ts in telethon_sessions))


if __name__ == "__main__":
    asyncio.run(main())
