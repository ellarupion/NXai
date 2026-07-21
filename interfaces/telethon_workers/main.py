"""Telethon ingest worker — точка входа для чтения чужих source_channels. Один
TelegramClient на одну активную TelethonSession, слушает только каналы,
которые панель к ней приписала (SourceChannel.ingest_session_id) — шардинг по
лимитам аккаунта заложен с самого начала.

Конфигурация горячо перечитывается (аудит, п.8.3): reconcile-цикл раз в
RELOAD_INTERVAL сверяет активные сессии и назначенные им каналы с
запущенными воркерами и запускает/останавливает/перезапускает их без рестарта
процесса. Смена набора каналов у сессии требует перезапуска её клиента —
events.NewMessage(chats=...) фиксирует список каналов при подписке.

Живой приём через events.NewMessage → IngestCandidatesService. Докачка
истории — отдельным job'ом планировщика (scheduler.py:backfill_job)."""

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
from core.services.heartbeat import WORKER_INGEST, record_heartbeat
from core.services.ingest_candidates import IncomingCandidate, IngestCandidatesService

logger = get_logger(__name__)

SUPERVISOR_BACKOFF_INITIAL_SECONDS = 5
SUPERVISOR_BACKOFF_MAX_SECONDS = 300
SUPERVISOR_STABLE_UPTIME_SECONDS = 600
HEARTBEAT_INTERVAL_SECONDS = 60
RELOAD_INTERVAL_SECONDS = 30


async def heartbeat_loop(count_fn) -> None:
    """Бьётся раз в минуту, пока процесс жив (аудит, п.3.1)."""
    while True:
        try:
            await record_heartbeat(WORKER_INGEST, detail=f"{count_fn()} сессия(й)")
        except Exception:
            logger.exception("telethon_worker.heartbeat_failed")
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def run_session_worker(
    session_string: str, source_chat_ids: list[int], settings: Settings
) -> None:
    client = TelegramClient(
        StringSession(session_string), settings.telegram_api_id, settings.telegram_api_hash
    )

    @client.on(events.NewMessage(chats=source_chat_ids))
    async def _on_new_message(event) -> None:  # noqa: ANN001 — telethon event type
        has_photo = event.message.photo is not None
        # Пропускаем только совсем пустые апдейты; пост-картинку принимаем (п.5.1).
        if not event.raw_text and not has_photo:
            return
        session_factory = get_session_factory()
        async with session_factory() as session:
            await IngestCandidatesService(session).receive_post(
                IncomingCandidate(
                    source_channel_tg_chat_id=event.chat_id,
                    tg_message_id=event.id,
                    text=event.raw_text or "",
                    posted_at=event.message.date,
                    has_media=has_photo,
                    media_group_id=event.message.grouped_id,
                )
            )
            await session.commit()

    await client.start()
    logger.info("telethon_worker.started", channel_count=len(source_chat_ids))
    await client.run_until_disconnected()


async def supervise_session_worker(
    session_id, session_string: str, source_chat_ids: list[int], settings: Settings
) -> None:
    """Перезапуск с бэкоффом — одна разлогиненная/сбойная сессия не роняет
    чтение остальных."""
    backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
    loop = asyncio.get_event_loop()
    while True:
        started_at = loop.time()
        try:
            await run_session_worker(session_string, source_chat_ids, settings)
            logger.warning("telethon_worker.disconnected", session_id=str(session_id))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("telethon_worker.crashed", session_id=str(session_id))
        if loop.time() - started_at > SUPERVISOR_STABLE_UPTIME_SECONDS:
            backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, SUPERVISOR_BACKOFF_MAX_SECONDS)


async def _load_session_configs() -> dict:
    """{session_id: (signature, session_string, [chat_ids])} активных сессий с
    хотя бы одним назначенным каналом. signature = (session_string, sorted
    chat_ids) — по её смене reconcile перезапускает воркер сессии."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        sessions = (
            await session.execute(select(TelethonSession).where(TelethonSession.is_active.is_(True)))
        ).scalars().all()
        configs = {}
        for ts in sessions:
            rows = await session.execute(
                select(SourceChannel.tg_chat_id).where(
                    SourceChannel.ingest_session_id == ts.id,
                    SourceChannel.is_active.is_(True),
                    SourceChannel.tg_chat_id.is_not(None),
                )
            )
            chat_ids = sorted(row[0] for row in rows.all())
            if not chat_ids:
                continue
            signature = (ts.session_string, tuple(chat_ids))
            configs[ts.id] = (signature, ts.session_string, chat_ids)
        return configs


async def reconcile_loop(tasks: dict, settings: Settings) -> None:
    """Держит набор запущенных сессий-воркеров в соответствии с БД (п.8.3)."""
    signatures: dict = {}
    while True:
        try:
            configs = await _load_session_configs()
        except Exception:
            logger.exception("telethon_worker.reconcile_load_failed")
            await asyncio.sleep(RELOAD_INTERVAL_SECONDS)
            continue

        for session_id in set(tasks) - set(configs):
            tasks.pop(session_id).cancel()
            signatures.pop(session_id, None)
            logger.info("telethon_worker.stopped_removed", session_id=str(session_id))

        for session_id, (signature, session_string, chat_ids) in configs.items():
            if session_id in tasks and signatures.get(session_id) == signature:
                continue
            if session_id in tasks:  # сменился набор каналов/сессия — перезапуск
                tasks.pop(session_id).cancel()
                logger.info("telethon_worker.restarting_changed", session_id=str(session_id))
            tasks[session_id] = asyncio.create_task(
                supervise_session_worker(session_id, session_string, chat_ids, settings)
            )
            signatures[session_id] = signature

        await asyncio.sleep(RELOAD_INTERVAL_SECONDS)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    session_factory = get_session_factory()
    async with session_factory() as session:
        effective_settings = await get_effective_settings(session)

    tasks: dict = {}
    await asyncio.gather(
        heartbeat_loop(lambda: len(tasks)),
        reconcile_loop(tasks, effective_settings),
    )


if __name__ == "__main__":
    asyncio.run(main())
