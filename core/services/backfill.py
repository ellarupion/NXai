"""Докачка истории одного source_channel через Telethon — общая логика для
двух входов: ручного ("Сделать посты" в панели, core/services/force_generate.py,
конкретная тема прямо сейчас) и периодического фонового job'а
(scheduler.py:backfill_job, все активные источники раз в
BACKFILL_INTERVAL_MINUTES). Без неё ingest видит только то, что происходит в
канале ПОСЛЕ того, как его добавили в панель (events.NewMessage) — источник с
редкими постами копил бы кандидатов месяцами, дожидаясь случайного live-поста,
а не набора реальной истории."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.logging import get_logger
from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.services.ingest_candidates import IncomingCandidate, IngestCandidatesService
from core.services.scoring import ScoringService
from core.statistics.client import PostStats, SourceStatsClient

logger = get_logger(__name__)

DEFAULT_BACKFILL_LIMIT = 30


async def backfill_source_channel(
    session: AsyncSession,
    source_channel: SourceChannel,
    settings: Settings,
    limit: int = DEFAULT_BACKFILL_LIMIT,
) -> int:
    """Возвращает число новых кандидатов, реально принятых ingest'ом за этот
    вызов (не считая уже виденных — IngestCandidatesService.receive_post
    идемпотентен по (source_channel_id, tg_message_id))."""
    if source_channel.ingest_session_id is None:
        return 0

    telethon_session = await session.get(TelethonSession, source_channel.ingest_session_id)
    if telethon_session is None:
        return 0

    client = SourceStatsClient(telethon_session.session_string, settings)
    try:
        await client.connect()
        messages = await client.get_messages_after(
            source_channel.tg_chat_id, source_channel.last_scanned_message_id or 0, limit=limit
        )
    except Exception:
        logger.exception("backfill.failed", source_channel_id=str(source_channel.id))
        return 0
    finally:
        await client.disconnect()

    ingest = IngestCandidatesService(session)
    scoring = ScoringService(session)

    received = 0
    for message in messages:
        if not message.text:
            continue
        candidate_id = await ingest.receive_post(
            IncomingCandidate(
                source_channel_tg_chat_id=source_channel.tg_chat_id,
                tg_message_id=message.tg_message_id,
                text=message.text,
            )
        )
        if candidate_id is None:
            continue
        received += 1
        if message.views is not None or message.forwards is not None:
            await scoring.record_snapshot(
                candidate_id,
                PostStats(views=message.views, forwards=message.forwards),
                datetime.now(timezone.utc),
            )

    if messages:
        # Ватермарка двигается даже если все сообщения в этой пачке оказались
        # уже виденными (received=0) — иначе backfill бесконечно перечитывал
        # бы один и тот же хвост истории на каждый тик.
        source_channel.last_scanned_message_id = max(m.tg_message_id for m in messages)
        source_channel.last_scanned_at = datetime.now(timezone.utc)
        await session.flush()

    return received
