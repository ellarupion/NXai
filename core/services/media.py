"""Докачка медиа кандидата в момент публикации (аудит, п.5.2).

Байты фото НЕ хранятся в БД — держим только ссылку (source_channel +
tg_message_id уже есть у кандидата, флаг has_media выставлен на ingest'е).
Здесь по этой ссылке через Telethon-сессию источника скачиваем фото поста,
чтобы publisher отправил их ботом. Скачивание отложено до публикации: качать
медиа для каждого увиденного поста (большинство отсеет скоринг) — пустая
трата трафика.

Если пост в источнике уже удалён или сессия недоступна — возвращаем пустой
список, вызывающая сторона публикует пост текстом (лучше, чем не опубликовать)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.statistics.client import SourceStatsClient

logger = get_logger(__name__)


async def download_candidate_photos(
    session: AsyncSession, candidate: CandidatePost, settings: Settings
) -> list[bytes]:
    """Возвращает байты фото кандидата (одиночное фото или все фото альбома),
    либо пустой список, если качать нечего/невозможно."""
    if not candidate.has_media:
        return []

    source_channel = await session.get(SourceChannel, candidate.source_channel_id)
    if source_channel is None or source_channel.ingest_session_id is None:
        return []
    telethon_session = await session.get(TelethonSession, source_channel.ingest_session_id)
    if telethon_session is None:
        return []

    client = SourceStatsClient(telethon_session.session_string, settings)
    try:
        await client.connect()
        media = await client.download_post_photos(
            source_channel.tg_chat_id, candidate.tg_message_id, candidate.media_group_id
        )
    except Exception:
        logger.exception("media.download_failed", candidate_id=str(candidate.id))
        return []
    finally:
        await client.disconnect()

    return [item.data for item in media]


async def download_candidate_photos_by_id(
    session: AsyncSession, candidate_id: UUID, settings: Settings
) -> list[bytes]:
    candidate = await session.get(CandidatePost, candidate_id)
    if candidate is None:
        return []
    return await download_candidate_photos(session, candidate, settings)
