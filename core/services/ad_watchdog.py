"""Ad Watchdog — детект и автоматическое перекрытие рекламных/чужих постов в
своих target_channels (адаптировано из NX core/services/foreign_post.py, см.
ARCHITECTURE.md §5). Ключевое отличие от NX: там это заканчивалось
предложением редактору в боте ("поставить наш пост следом?"), здесь —
`cover_if_due` полностью автоматический шаг планировщика, без подтверждения."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.ad_detection import AdDetection
from core.models.enums import AdDetectionAction
from core.models.publication import Publication
from core.models.target_channel import TargetChannel
from core.services.publisher import PublisherService
from core.services.scheduler_pool import SchedulerPoolService

logger = get_logger(__name__)

COVER_DELAY = timedelta(hours=1)


async def detect_foreign_post(
    session: AsyncSession, tg_chat_id: int, tg_message_id: int
) -> TargetChannel | None:
    """Возвращает TargetChannel, если апдейт пришёл из активного целевого
    канала темы и это не наша собственная публикация (Publication с таким
    tg_message_id ещё нет) — иначе None."""
    result = await session.execute(
        select(TargetChannel).where(
            TargetChannel.tg_chat_id == tg_chat_id, TargetChannel.is_active.is_(True)
        )
    )
    target_channel = result.scalar_one_or_none()
    if target_channel is None:
        return None

    known = await session.scalar(
        select(Publication.id).where(
            Publication.target_channel_id == target_channel.id,
            Publication.tg_message_id == tg_message_id,
        )
    )
    if known is not None:
        return None

    return target_channel


async def record_detection(
    session: AsyncSession, target_channel_id: UUID, tg_message_id: int
) -> AdDetection:
    detection = AdDetection(
        target_channel_id=target_channel_id,
        tg_message_id=tg_message_id,
        detected_at=datetime.now(timezone.utc),
    )
    session.add(detection)
    await session.flush()
    logger.info("ad_watchdog.detected", ad_detection_id=str(detection.id), target_channel_id=str(target_channel_id))
    return detection


async def cover_if_due(
    session: AsyncSession, bot: Bot, ad_detection_id: UUID, now: datetime | None = None
) -> bool:
    """Вызывается периодическим тиком планировщика (ROADMAP.md Phase 4) для
    каждого PENDING-детекта: если прошёл COVER_DELAY, публикует лучший READY
    pool_post темы поверх рекламы. Возвращает True, если перекрытие
    произошло сейчас."""
    now = now or datetime.now(timezone.utc)
    detection = await session.get(AdDetection, ad_detection_id, with_for_update=True)
    if detection is None or detection.action is not AdDetectionAction.PENDING:
        return False
    if now - detection.detected_at < COVER_DELAY:
        return False

    target_channel = await session.get(TargetChannel, detection.target_channel_id)
    if target_channel is None or not target_channel.is_active:
        detection.action = AdDetectionAction.IGNORED
        await session.flush()
        return False

    next_post = await SchedulerPoolService(session).pick_pool_post(target_channel.theme_id)
    if next_post is None:
        logger.warning("ad_watchdog.no_pool_post_available", target_channel_id=str(target_channel.id))
        return False

    publication = await PublisherService(session).publish_pool_post(
        bot, next_post.id, target_channel.id, is_ad_cover=True
    )
    detection.action = AdDetectionAction.AUTO_BURIED
    detection.covering_publication_id = publication.id
    await session.flush()

    logger.info(
        "ad_watchdog.covered",
        ad_detection_id=str(detection.id),
        covering_publication_id=str(publication.id),
    )
    return True
