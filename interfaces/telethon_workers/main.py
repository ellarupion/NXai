"""Telethon ingest worker — точка входа для чтения чужих source_channels (см.
ARCHITECTURE.md §2, §7). Один TelegramClient на одну активную
TelethonSession, слушает только каналы, которые панель к ней приписала
(SourceChannel.ingest_session_id) — так шардинг по лимитам аккаунта
(число каналов, частота GetHistoryRequest) заложен с самого начала, а не
добавляется поверх одной раздутой сессии.

Реализовано: живой приём через events.NewMessage → IngestCandidatesService.
Докачка истории (при добавлении нового source_channel или после простоя
ingest-воркера) — НЕ здесь, а отдельным периодическим job'ом планировщика
(scheduler.py:backfill_job → core/services/backfill.py, тот же принцип,
что backfill в NX, но не завязан на этот процесс): так подхватывается даже
если сам ingest-воркер долго не поднимался."""

import asyncio

from sqlalchemy import select
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from core.config import Settings, get_settings
from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.services.effective_settings import get_effective_settings
from core.services.ingest_candidates import IncomingCandidate, IngestCandidatesService

logger = get_logger(__name__)

SUPERVISOR_BACKOFF_INITIAL_SECONDS = 5
SUPERVISOR_BACKOFF_MAX_SECONDS = 300
SUPERVISOR_STABLE_UPTIME_SECONDS = 600


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


async def run_session_worker(telethon_session: TelethonSession, settings: Settings) -> None:
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
                    posted_at=event.message.date,
                )
            )
            await session.commit()

    await client.start()
    logger.info(
        "telethon_worker.started", session_label=telethon_session.label, channel_count=len(source_chat_ids)
    )
    await client.run_until_disconnected()


async def supervise_session_worker(telethon_session: TelethonSession, settings: Settings) -> None:
    """Перезапуск с бэкоффом — одна разлогиненная/сбойная сессия не роняет
    чтение остальных (раньше gather падал целиком по первому исключению)."""
    backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
    loop = asyncio.get_event_loop()
    while True:
        started_at = loop.time()
        try:
            await run_session_worker(telethon_session, settings)
            # run_session_worker возвращается без исключения, только если у
            # сессии нет назначенных каналов — рестартовать нечего.
            logger.info("telethon_worker.no_channels_exit", session_label=telethon_session.label)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("telethon_worker.crashed", session_label=telethon_session.label)
        if loop.time() - started_at > SUPERVISOR_STABLE_UPTIME_SECONDS:
            backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
        logger.info(
            "telethon_worker.restart_scheduled",
            session_label=telethon_session.label,
            backoff_seconds=backoff,
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, SUPERVISOR_BACKOFF_MAX_SECONDS)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Один раз при старте процесса (не per-tick, в отличие от scheduler.py) —
        # long-polling воркер и так требует рестарта, чтобы подхватить новый
        # оверрайд из панели, поэтому фиксируем settings на весь run.
        effective_settings = await get_effective_settings(session)
        result = await session.execute(select(TelethonSession).where(TelethonSession.is_active.is_(True)))
        telethon_sessions = list(result.scalars().all())

    if not telethon_sessions:
        logger.warning("telethon_worker.no_active_sessions")
        return

    await asyncio.gather(*(supervise_session_worker(ts, effective_settings) for ts in telethon_sessions))


if __name__ == "__main__":
    asyncio.run(main())
