"""channel_post-хендлер, общий для всех тематических ботов (см.
interfaces/bots/main.py) — детект чужого/рекламного поста в целевом канале
темы. core/services/ad_watchdog.py.detect_foreign_post уже отфильтровывает
свои собственные публикации (по Publication.tg_message_id), поэтому сюда
долетают только реально посторонние сообщения."""

from aiogram import Router
from aiogram.types import Message

from core.db import get_session_factory
from core.logging import get_logger
from core.services.ad_watchdog import detect_foreign_post, record_detection

logger = get_logger(__name__)

router = Router(name="ad-watchdog")


@router.channel_post()
async def on_channel_post(message: Message) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        target_channel = await detect_foreign_post(session, message.chat.id, message.message_id)
        if target_channel is None:
            return

        await record_detection(session, target_channel.id, message.message_id)
        await session.commit()
        logger.info(
            "ad_watchdog.foreign_post_detected",
            target_channel_id=str(target_channel.id),
            tg_message_id=message.message_id,
        )
