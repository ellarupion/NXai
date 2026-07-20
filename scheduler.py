"""Точка входа для периодических задач (APScheduler, in-process — тот же
подход, что в NX: Celery добавляется вторым этапом только при реальной
нагрузке). В отличие от NX (один бот на процесс), здесь на каждый тик
приходится решать, за какую тему/канал идёт работа — Bot и Telethon-клиент
создаются здесь короткоживущими, per-tick, а не одним долгоживущим
инстансом на весь процесс (см. ARCHITECTURE.md §2)."""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from core.config import get_settings
from core.db import get_session_factory
from core.embeddings.client import EmbeddingsClient
from core.llm.client import LLMClient
from core.logging import configure_logging, get_logger
from core.models.ad_detection import AdDetection
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import AdDetectionAction, BotRole, CandidatePostStatus
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.telethon_session import TelethonSession
from core.services.ad_watchdog import cover_if_due
from core.services.dedup import DedupService
from core.services.publisher import PublisherService
from core.services.rewrite import RewriteService
from core.services.scheduler_pool import SchedulerPoolService, is_due
from core.services.scoring import ScoringService
from core.statistics.client import SourceStatsClient

logger = get_logger(__name__)

SCORE_REFRESH_INTERVAL_MINUTES = 10
DEDUP_REWRITE_INTERVAL_MINUTES = 5
PUBLISH_POOL_INTERVAL_SECONDS = 60
AD_WATCHDOG_INTERVAL_MINUTES = 5


async def score_refresh_job() -> None:
    """Переопрашивает views/forwards у NEW/SCORING-кандидатов, чьи контрольные
    точки (+30м/+2ч/+6ч) наступили, через Telethon-сессию их source_channel
    (см. core/models/source_channel.py:ingest_session_id). Кандидаты без
    назначенной сессии пропускаются — панель должна была назначить её при
    добавлении канала (ROADMAP.md Phase 1)."""
    session_factory = get_session_factory()
    scored = 0
    async with session_factory() as session:
        result = await session.execute(
            select(CandidatePost).where(
                CandidatePost.status.in_([CandidatePostStatus.NEW, CandidatePostStatus.SCORING])
            )
        )
        candidates = list(result.scalars().all())

        scoring = ScoringService(session)
        due = [c for c in candidates if await scoring.is_checkpoint_due(c)]
        if not due:
            return

        stats_clients: dict[str, SourceStatsClient] = {}
        try:
            for candidate in due:
                source_channel = await session.get(SourceChannel, candidate.source_channel_id)
                if source_channel is None or source_channel.ingest_session_id is None:
                    continue

                session_id = str(source_channel.ingest_session_id)
                if session_id not in stats_clients:
                    telethon_session = await session.get(TelethonSession, source_channel.ingest_session_id)
                    if telethon_session is None:
                        continue
                    client = SourceStatsClient(telethon_session.session_string)
                    await client.connect()
                    stats_clients[session_id] = client

                stats = await stats_clients[session_id].get_post_stats(
                    source_channel.tg_chat_id, candidate.tg_message_id
                )
                if stats is None:
                    continue
                await scoring.record_snapshot(candidate.id, stats, datetime.now(timezone.utc))
                await scoring.promote_if_selected(candidate.id)
                scored += 1
        finally:
            for client in stats_clients.values():
                await client.disconnect()
        await session.commit()

    if scored:
        logger.info("scheduler.score_refresh_done", scored=scored)


async def dedup_and_rewrite_job() -> None:
    """SELECTED-кандидаты: сначала дедуп внутри темы (дёшево), потом рерайт
    LLM только для тех, кто не свернулся в дубликат (дорого) — порядок
    важен для стоимости, см. ARCHITECTURE.md §5/§7."""
    settings = get_settings()
    llm = LLMClient(settings)
    embeddings = EmbeddingsClient(settings)

    session_factory = get_session_factory()
    rewritten = 0
    async with session_factory() as session:
        result = await session.execute(
            select(CandidatePost, SourceChannel)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(CandidatePost.status == CandidatePostStatus.SELECTED)
        )
        rows = result.all()

        dedup = DedupService(session, embeddings)
        rewrite = RewriteService(session, llm, embeddings)
        for candidate, source_channel in rows:
            if source_channel.theme_id is None:
                continue
            duplicate_of = await dedup.resolve_duplicates(candidate.id, source_channel.theme_id)
            if duplicate_of is not None:
                continue

            channel_bot_result = await session.execute(
                select(ChannelBot).where(
                    ChannelBot.theme_id == source_channel.theme_id, ChannelBot.role == BotRole.THEME
                )
            )
            channel_bot = channel_bot_result.scalar_one_or_none()
            persona_prompt = channel_bot.persona_prompt if channel_bot else ""
            try:
                await rewrite.generate(candidate.id, persona_prompt)
                rewritten += 1
            except Exception:
                logger.exception("scheduler.rewrite_failed", candidate_id=str(candidate.id))
        await session.commit()

    if rewritten:
        logger.info("scheduler.dedup_and_rewrite_done", rewritten=rewritten)


async def publish_pool_job() -> None:
    """Для каждого активного тематического бота: если пора публиковать
    (каданс/тихие часы/джиттер — см. core/services/scheduler_pool.py), берёт
    следующий пост (взвешенно-случайно, не FIFO) и публикует в целевые
    каналы темы."""
    session_factory = get_session_factory()
    published = 0
    async with session_factory() as session:
        result = await session.execute(
            select(ChannelBot).where(ChannelBot.role == BotRole.THEME, ChannelBot.is_active.is_(True))
        )
        theme_bots = list(result.scalars().all())

        for channel_bot in theme_bots:
            if channel_bot.theme_id is None:
                continue
            target_result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.theme_id == channel_bot.theme_id, TargetChannel.is_active.is_(True)
                )
            )
            target_channels = list(target_result.scalars().all())
            if not target_channels:
                continue

            last_publication = await _last_publication_at(session, [tc.id for tc in target_channels])
            if not is_due(channel_bot.cadence, last_publication):
                continue

            next_post = await SchedulerPoolService(session).pick_next(channel_bot.theme_id)
            if next_post is None:
                continue

            async with Bot(token=channel_bot.bot_token) as bot:
                publisher = PublisherService(session)
                target_channel = target_channels[0]
                try:
                    if next_post.kind == "candidate":
                        await publisher.publish_candidate(bot, next_post.id, target_channel.id)
                    else:
                        await publisher.publish_pool_post(bot, next_post.id, target_channel.id)
                    published += 1
                except Exception:
                    logger.exception("scheduler.publish_failed", channel_bot_id=str(channel_bot.id))
        await session.commit()

    if published:
        logger.info("scheduler.publish_pool_done", published=published)


async def ad_watchdog_job() -> None:
    session_factory = get_session_factory()
    covered = 0
    async with session_factory() as session:
        result = await session.execute(
            select(AdDetection).where(AdDetection.action == AdDetectionAction.PENDING)
        )
        pending = list(result.scalars().all())

        for detection in pending:
            target_channel = await session.get(TargetChannel, detection.target_channel_id)
            if target_channel is None:
                continue
            channel_bot_result = await session.execute(
                select(ChannelBot).where(
                    ChannelBot.theme_id == target_channel.theme_id, ChannelBot.role == BotRole.THEME
                )
            )
            channel_bot = channel_bot_result.scalar_one_or_none()
            if channel_bot is None:
                continue

            async with Bot(token=channel_bot.bot_token) as bot:
                if await cover_if_due(session, bot, detection.id):
                    covered += 1
        await session.commit()

    if covered:
        logger.info("scheduler.ad_watchdog_done", covered=covered)


async def _last_publication_at(session, target_channel_ids: list) -> datetime | None:
    from core.models.publication import Publication

    if not target_channel_ids:
        return None
    result = await session.execute(
        select(Publication.published_at)
        .where(Publication.target_channel_id.in_(target_channel_ids))
        .order_by(Publication.published_at.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        score_refresh_job, "interval", minutes=SCORE_REFRESH_INTERVAL_MINUTES,
        id="score_refresh", max_instances=1,
    )
    scheduler.add_job(
        dedup_and_rewrite_job, "interval", minutes=DEDUP_REWRITE_INTERVAL_MINUTES,
        id="dedup_and_rewrite", max_instances=1,
    )
    scheduler.add_job(
        publish_pool_job, "interval", seconds=PUBLISH_POOL_INTERVAL_SECONDS,
        id="publish_pool", max_instances=1,
    )
    scheduler.add_job(
        ad_watchdog_job, "interval", minutes=AD_WATCHDOG_INTERVAL_MINUTES,
        id="ad_watchdog", max_instances=1,
    )

    # TODO(ROADMAP.md Phase 5): metrics_collection_job (AnalyticsService,
    # PublicationMetricsSnapshot) и дайджесты в admin-бота — требуют выделенной
    # Telethon-сессии, состоящей в целевых каналах, и опроса ChannelBot(role=ADMIN).

    return scheduler


async def run_forever() -> None:
    settings = get_settings()
    configure_logging(settings)

    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler.started", jobs=len(scheduler.get_jobs()))
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run_forever())
