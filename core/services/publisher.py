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


class NotPublishableError(Exception):
    pass


class PublisherService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish_candidate(
        self, bot: Bot, candidate_id: UUID, target_channel_id: UUID
    ) -> Publication:
        candidate = await self.session.get(CandidatePost, candidate_id, with_for_update=True)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if candidate.status is not CandidatePostStatus.REWRITTEN:
            raise NotPublishableError(f"CandidatePost {candidate.id} is {candidate.status.value}, expected rewritten")
        if candidate.selected_post_version_id is None:
            raise NotPublishableError(f"CandidatePost {candidate.id} has no post_version")

        post_version = await self.session.get(PostVersion, candidate.selected_post_version_id)
        target_channel = await self._get_target_channel(target_channel_id)

        text = post_version.rewritten_text
        if target_channel.signature:
            text = f"{text}\n\n{target_channel.signature}"

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
        candidate.status = CandidatePostStatus.PUBLISHED
        await self.session.flush()

        logger.info(
            "publisher.candidate_published",
            candidate_id=str(candidate.id),
            target_channel_id=str(target_channel.id),
        )
        return publication

    async def publish_pool_post(
        self, bot: Bot, pool_post_id: UUID, target_channel_id: UUID, is_ad_cover: bool = False
    ) -> Publication:
        pool_post = await self.session.get(PoolPost, pool_post_id, with_for_update=True)
        if pool_post is None:
            raise ValueError(f"PoolPost {pool_post_id} not found")
        if pool_post.status is not PoolPostStatus.READY:
            raise NotPublishableError(f"PoolPost {pool_post.id} is {pool_post.status.value}, expected ready")

        target_channel = await self._get_target_channel(target_channel_id)

        text = pool_post.text
        if target_channel.signature:
            text = f"{text}\n\n{target_channel.signature}"

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
        # pool_posts переиспользуемы (в отличие от candidate_posts) — статус
        # возвращается в READY, times_used растёт, см. core/models/pool_post.py.
        pool_post.times_used += 1
        pool_post.last_used_at = publication.published_at
        await self.session.flush()

        logger.info(
            "publisher.pool_post_published",
            pool_post_id=str(pool_post.id),
            target_channel_id=str(target_channel.id),
            is_ad_cover=is_ad_cover,
        )
        return publication

    async def _get_target_channel(self, target_channel_id: UUID) -> TargetChannel:
        target_channel = await self.session.get(TargetChannel, target_channel_id)
        if target_channel is None:
            raise ValueError(f"TargetChannel {target_channel_id} not found")
        return target_channel
