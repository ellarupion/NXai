"""PublisherService — публикация через официальный Bot API (адаптировано из NX
core/services/publisher.py). Publication — факт публикации, не намерение:
строка появляется только в момент реальной успешной отправки. В отличие от
NX, здесь два независимых входа — publish_candidate (рерайт кандидата,
обычный тематический пост) и publish_pool_post (свой запасной пул: обычное
заполнение расписания ИЛИ ad-cover, is_ad_cover=True — см.
core/services/ad_watchdog.py), а не одна универсальная publish_now от Draft."""

from datetime import datetime, timezone
from uuid import UUID

from aiogram import Bot
from aiogram.types import LinkPreviewOptions
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus, PoolPostStatus, PublicationSource
from core.models.pool_post import PoolPost
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.target_channel import TargetChannel

logger = get_logger(__name__)

# Жёсткий лимит Bot API на текстовое сообщение. Промпт рерайта просит держаться
# заметно короче (core/services/rewrite.py), но LLM это не гарантия — перед
# отправкой обрезаем защитно, иначе send_message падает и публикация теряется.
TELEGRAM_MAX_TEXT = 4096
TRUNCATION_ELLIPSIS = "…"


def fit_to_telegram_limit(text: str, signature: str = "") -> str:
    """Собирает текст с подписью и, если он не влезает в лимит Telegram,
    обрезает ОСНОВНОЙ текст по границе слова (подпись сохраняется целиком)."""
    full = f"{text}\n\n{signature}" if signature else text
    if len(full) <= TELEGRAM_MAX_TEXT:
        return full

    overhead = (len(signature) + 2 if signature else 0) + len(TRUNCATION_ELLIPSIS)
    budget = TELEGRAM_MAX_TEXT - overhead
    cut = text[:budget]
    last_space = cut.rfind(" ")
    if last_space > budget // 2:
        cut = cut[:last_space]
    truncated = f"{cut}{TRUNCATION_ELLIPSIS}"
    logger.warning("publisher.text_truncated", original_len=len(text), truncated_len=len(truncated))
    return f"{truncated}\n\n{signature}" if signature else truncated


class NotPublishableError(Exception):
    pass


class PublisherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish_candidate(
        self, bot: Bot, candidate_id: UUID, target_channel_id: UUID
    ) -> Publication:
        """Одна цель — обёртка над publish_candidate_to_channels для обратной
        совместимости и тестов."""
        publications = await self.publish_candidate_to_channels(
            bot, candidate_id, [target_channel_id]
        )
        return publications[0]

    async def publish_candidate_to_channels(
        self, bot: Bot, candidate_id: UUID, target_channel_ids: list[UUID]
    ) -> list[Publication]:
        """Публикует рерайт кандидата во ВСЕ переданные целевые каналы темы
        (аудит, баг №5: раньше публиковалось только в target_channels[0], и
        вторые каналы темы никогда ничего не получали). Статус кандидата
        переводится в PUBLISHED один раз после отправки во все каналы —
        каждый канал получает свою строку Publication."""
        candidate = await self.session.get(CandidatePost, candidate_id, with_for_update=True)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if candidate.status is not CandidatePostStatus.REWRITTEN:
            raise NotPublishableError(f"CandidatePost {candidate.id} is {candidate.status.value}, expected rewritten")
        if candidate.selected_post_version_id is None:
            raise NotPublishableError(f"CandidatePost {candidate.id} has no post_version")

        post_version = await self.session.get(PostVersion, candidate.selected_post_version_id)

        publications: list[Publication] = []
        for target_channel_id in target_channel_ids:
            target_channel = await self._get_target_channel(target_channel_id)
            text = fit_to_telegram_limit(post_version.rewritten_text, target_channel.signature)
            message = await bot.send_message(
                target_channel.tg_chat_id, text, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            publication = Publication(
                target_channel_id=target_channel.id,
                source=PublicationSource.CANDIDATE,
                post_version_id=post_version.id,
                tg_message_id=message.message_id,
                published_at=datetime.now(timezone.utc),
            )
            self.session.add(publication)
            publications.append(publication)
            logger.info(
                "publisher.candidate_published",
                candidate_id=str(candidate.id),
                target_channel_id=str(target_channel.id),
            )

        candidate.status = CandidatePostStatus.PUBLISHED
        await self.session.flush()
        return publications

    async def publish_pool_post(
        self, bot: Bot, pool_post_id: UUID, target_channel_id: UUID, is_ad_cover: bool = False
    ) -> Publication:
        """Одна цель. Используется ad watchdog'ом (перекрытие рекламы в одном
        конкретном канале) и как обёртка для publish_pool_post_to_channels."""
        publications = await self.publish_pool_post_to_channels(
            bot, pool_post_id, [target_channel_id], is_ad_cover=is_ad_cover
        )
        return publications[0]

    async def publish_pool_post_to_channels(
        self,
        bot: Bot,
        pool_post_id: UUID,
        target_channel_ids: list[UUID],
        is_ad_cover: bool = False,
    ) -> list[Publication]:
        pool_post = await self.session.get(PoolPost, pool_post_id, with_for_update=True)
        if pool_post is None:
            raise ValueError(f"PoolPost {pool_post_id} not found")
        if pool_post.status is not PoolPostStatus.READY:
            raise NotPublishableError(f"PoolPost {pool_post.id} is {pool_post.status.value}, expected ready")

        publications: list[Publication] = []
        for target_channel_id in target_channel_ids:
            target_channel = await self._get_target_channel(target_channel_id)
            text = fit_to_telegram_limit(pool_post.text, target_channel.signature)
            message = await bot.send_message(
                target_channel.tg_chat_id, text, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            publication = Publication(
                target_channel_id=target_channel.id,
                source=PublicationSource.POOL,
                pool_post_id=pool_post.id,
                tg_message_id=message.message_id,
                published_at=datetime.now(timezone.utc),
                is_ad_cover=is_ad_cover,
            )
            self.session.add(publication)
            publications.append(publication)
            # pool_posts переиспользуемы (в отличие от candidate_posts) — статус
            # остаётся READY, times_used растёт per-publication.
            pool_post.times_used += 1
            pool_post.last_used_at = publication.published_at
            logger.info(
                "publisher.pool_post_published",
                pool_post_id=str(pool_post.id),
                target_channel_id=str(target_channel.id),
                is_ad_cover=is_ad_cover,
            )

        await self.session.flush()
        return publications

    async def _get_target_channel(self, target_channel_id: UUID) -> TargetChannel:
        target_channel = await self.session.get(TargetChannel, target_channel_id)
        if target_channel is None:
            raise ValueError(f"TargetChannel {target_channel_id} not found")
        return target_channel
