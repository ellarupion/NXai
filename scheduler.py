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
from telethon.errors import FloodWaitError

from core.config import get_settings
from core.db import get_session_factory
from core.embeddings.client import EmbeddingsClient
from core.llm.client import LLMClient
from core.logging import configure_logging, get_logger
from core.models.ad_detection import AdDetection
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import AdDetectionAction, BotRole, CandidatePostStatus
from core.models.pool_post import PoolPost
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.telethon_session import TelethonSession
from core.models.theme import Theme
from core.services.ad_watchdog import cover_if_due
from core.services.admin_notify import (
    AdCoveredNotification,
    PublishedNotification,
    format_ad_covered,
    format_error,
    format_published,
)
from core.services.backfill import backfill_source_channel
from core.services.dedup import DedupService
from core.services.effective_settings import get_effective_settings
from core.services.heartbeat import WORKER_SCHEDULER, record_heartbeat
from core.services.media import download_candidate_photos
from core.services.panel_settings import get_or_create_panel_settings
from core.services.publisher import PublisherService
from core.services.rewrite import RewriteService
from core.services.scheduler_pool import SchedulerPoolService, is_due, resolve_zoneinfo
from core.services.scoring import ScoringService
from core.statistics.client import SourceStatsClient

logger = get_logger(__name__)

BACKFILL_INTERVAL_MINUTES = 15
SCORE_REFRESH_INTERVAL_MINUTES = 10
DEDUP_REWRITE_INTERVAL_MINUTES = 5
PUBLISH_POOL_INTERVAL_SECONDS = 60
AD_WATCHDOG_INTERVAL_MINUTES = 5
HEARTBEAT_INTERVAL_SECONDS = 60


async def heartbeat_job() -> None:
    """Отметка живости процесса scheduler (аудит, п.3.1) — панель по ней
    отличает «пайплайн работает» от «процесс упал/завис»."""
    try:
        await record_heartbeat(WORKER_SCHEDULER)
    except Exception:
        logger.exception("scheduler.heartbeat_failed")


async def backfill_job() -> None:
    """Периодическая докачка истории всех активных источников с назначенной
    сессией-читалкой (core/services/backfill.py) — без этого ingest видит
    только live-апдейты, случившиеся ПОСЛЕ добавления канала в панель, и
    источник с редкими постами копил бы кандидатов месяцами. До этого job'а
    докачка происходила только вручную, по кнопке «Сделать посты»
    (core/services/force_generate.py)."""
    session_factory = get_session_factory()
    received_total = 0
    async with session_factory() as session:
        settings = await get_effective_settings(session)
        result = await session.execute(
            select(SourceChannel).where(
                SourceChannel.is_active.is_(True), SourceChannel.ingest_session_id.is_not(None)
            )
        )
        source_channels = list(result.scalars().all())

        # Коммит на каждый источник, а не в конце тика: сбой на N-м канале не
        # должен терять уже докачанное с первых N-1 (тот же принцип во всех
        # джобах этого файла — см. аудит, К4).
        for source_channel in source_channels:
            try:
                received_total += await backfill_source_channel(session, source_channel, settings)
                await session.commit()
            except Exception:
                logger.exception("scheduler.backfill_source_failed", source_channel_id=str(source_channel.id))
                await session.rollback()

    if received_total:
        logger.info("scheduler.backfill_done", received=received_total)


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

        # Telegram api_id/api_hash тоже берутся per-tick (см. dedup_and_rewrite_job
        # ниже) — оверрайд из панели (core/services/effective_settings.py)
        # подхватывается без рестарта scheduler'а.
        settings = await get_effective_settings(session)

        stats_clients: dict[str, SourceStatsClient] = {}
        # Сессии, поймавшие FloodWait в этом тике: их кандидатов пропускаем до
        # следующего тика (через 10 минут), а не молотим дальше, усугубляя бан.
        flooded_sessions: set[str] = set()
        # Идентификаторы вытаскиваем ДО цикла: commit/rollback per-candidate
        # экспайрит ORM-объекты, и последующий доступ к их атрибутам
        # (candidate.source_channel_id и т.п.) вызвал бы ленивую подгрузку —
        # синхронное IO под asyncpg падает MissingGreenlet. Внутри цикла
        # работаем со скалярами и заново берём объект через session.get.
        due_ids = [c.id for c in due]
        try:
            for candidate_id in due_ids:
                try:
                    candidate = await session.get(CandidatePost, candidate_id)
                    if candidate is None:
                        continue
                    source_channel = await session.get(SourceChannel, candidate.source_channel_id)
                    if source_channel is None or source_channel.ingest_session_id is None:
                        continue

                    session_id = str(source_channel.ingest_session_id)
                    if session_id in flooded_sessions:
                        continue
                    if session_id not in stats_clients:
                        telethon_session = await session.get(
                            TelethonSession, source_channel.ingest_session_id
                        )
                        if telethon_session is None:
                            continue
                        client = SourceStatsClient(telethon_session.session_string, settings)
                        await client.connect()
                        stats_clients[session_id] = client

                    stats = await stats_clients[session_id].get_post_stats(
                        source_channel.tg_chat_id, candidate.tg_message_id
                    )
                    if stats is None:
                        continue
                    await scoring.record_snapshot(candidate.id, stats, datetime.now(timezone.utc))
                    if not await scoring.promote_if_selected(candidate.id):
                        await scoring.reject_if_matured(candidate)
                    scored += 1
                    # Коммит на кандидата: одна ошибка дальше по списку не
                    # откатывает уже записанные снапшоты этого тика.
                    await session.commit()
                except FloodWaitError as exc:
                    await session.rollback()
                    # ingest_session_id уже строка выше — но после rollback объект
                    # экспайрен, поэтому в set кладём заранее вычисленный session_id.
                    flooded_sessions.add(session_id)
                    logger.warning(
                        "scheduler.score_refresh_flood_wait",
                        session_id=session_id,
                        wait_seconds=exc.seconds,
                    )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "scheduler.score_refresh_candidate_failed", candidate_id=str(candidate_id)
                    )
        finally:
            for client in stats_clients.values():
                await client.disconnect()

    if scored:
        logger.info("scheduler.score_refresh_done", scored=scored)


async def dedup_and_rewrite_job() -> None:
    """SELECTED-кандидаты: сначала дедуп внутри темы (дёшево), потом рерайт
    LLM только для тех, кто не свернулся в дубликат (дорого) — порядок
    важен для стоимости, см. ARCHITECTURE.md §5/§7."""
    session_factory = get_session_factory()
    rewritten = 0
    async with session_factory() as session:
        # Ключи берутся per-tick (не в module-level get_settings()), чтобы
        # смена оверрайда в панели подхватывалась без рестарта scheduler'а
        # (core/services/effective_settings.py — DB-оверрайд поверх .env).
        settings = await get_effective_settings(session)
        llm = LLMClient(settings)
        embeddings = EmbeddingsClient(settings)

        result = await session.execute(
            select(CandidatePost.id, SourceChannel.theme_id)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(CandidatePost.status == CandidatePostStatus.SELECTED)
        )
        # Скаляры, а не ORM-объекты: commit/rollback per-candidate экспайрит
        # объекты, и повторный доступ к их атрибутам ленивой подгрузкой упал бы
        # MissingGreenlet под asyncpg (та же причина, что в score_refresh_job).
        rows = [(candidate_id, theme_id) for candidate_id, theme_id in result.all()]

        dedup = DedupService(session, embeddings)
        rewrite = RewriteService(session, llm, embeddings)
        for candidate_id, theme_id in rows:
            if theme_id is None:
                continue
            # try/except покрывает и дедуп (Voyage API умеет падать так же, как
            # LLM), и рерайт; коммит на кандидата — ошибка на одном не теряет
            # уже готовые рерайты этого тика.
            try:
                duplicate_of = await dedup.resolve_duplicates(candidate_id, theme_id)
                if duplicate_of is not None:
                    await session.commit()
                    continue

                channel_bot_result = await session.execute(
                    select(ChannelBot).where(
                        ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
                    )
                )
                channel_bot = channel_bot_result.scalar_one_or_none()
                persona_prompt = channel_bot.persona_prompt if channel_bot else ""
                await rewrite.generate(candidate_id, persona_prompt)
                rewritten += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception("scheduler.rewrite_failed", candidate_id=str(candidate_id))
                theme = await session.get(Theme, theme_id)
                await _notify_admin(
                    session, format_error(theme.name if theme else "", "рерайте", str(exc))
                )

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
        # Таймзона проекта — для расчёта тихих часов (аудит, К3). Читаем раз на
        # тик; смена в панели подхватывается со следующего тика без рестарта.
        panel_settings = await get_or_create_panel_settings(session)
        tz = resolve_zoneinfo(panel_settings.timezone)
        pool_cooldown_days = panel_settings.pool_cooldown_days
        # Telegram-креды для докачки медиа кандидатов (core/services/media.py).
        settings = await get_effective_settings(session)

        result = await session.execute(
            select(ChannelBot.id).where(
                ChannelBot.role == BotRole.THEME, ChannelBot.is_active.is_(True)
            )
        )
        # Скаляры + re-get внутри цикла: per-bot commit/rollback экспайрит
        # ORM-объекты, дальнейший доступ к атрибутам упал бы MissingGreenlet.
        bot_ids = [bot_id for (bot_id,) in result.all()]

        for bot_id in bot_ids:
            channel_bot = await session.get(ChannelBot, bot_id)
            if channel_bot is None or channel_bot.theme_id is None:
                continue
            theme_id = channel_bot.theme_id
            cadence = channel_bot.cadence
            bot_token = channel_bot.bot_token

            target_result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.theme_id == theme_id, TargetChannel.is_active.is_(True)
                )
            )
            target_channels = list(target_result.scalars().all())
            if not target_channels:
                continue

            target_channel_ids = [tc.id for tc in target_channels]
            target_titles = ", ".join(tc.title for tc in target_channels)
            last_publication = await _last_publication_at(session, target_channel_ids)
            if not is_due(cadence, last_publication, tz=tz):
                continue

            next_post = await SchedulerPoolService(session).pick_next(
                theme_id, pool_cooldown_days=pool_cooldown_days
            )
            if next_post is None:
                continue

            async with Bot(token=bot_token) as bot:
                publisher = PublisherService(session)
                theme = await session.get(Theme, theme_id)
                theme_name = theme.name if theme else ""
                try:
                    preview_text = await _preview_text_for(session, next_post)
                    # Публикуем во ВСЕ активные целевые каналы темы, а не только
                    # в первый (аудит, баг №5).
                    if next_post.kind == "candidate":
                        # Если у поста было фото — докачиваем его из источника и
                        # публикуем с картинкой (аудит, п.5.2); при неудаче
                        # download вернёт [], пост уйдёт текстом.
                        candidate = await session.get(CandidatePost, next_post.id)
                        photos = (
                            await download_candidate_photos(session, candidate, settings)
                            if candidate and candidate.has_media
                            else []
                        )
                        await publisher.publish_candidate_to_channels(
                            bot, next_post.id, target_channel_ids, photos=photos
                        )
                    else:
                        await publisher.publish_pool_post_to_channels(
                            bot, next_post.id, target_channel_ids
                        )
                    # Коммит СРАЗУ после успешной отправки, до уведомлений: пост
                    # уже в Telegram, и незакоммиченная Publication — это (а) дубль
                    # при рестарте процесса и (б) окно гонки, в котором ad watchdog
                    # принимает собственную публикацию за чужую (аудит, К1).
                    await session.commit()
                    published += 1
                    await _notify_admin(
                        session,
                        format_published(
                            PublishedNotification(
                                theme_name=theme_name,
                                target_channel_title=target_titles,
                                preview_text=preview_text,
                            )
                        ),
                    )
                except Exception as exc:
                    await session.rollback()
                    logger.exception("scheduler.publish_failed", channel_bot_id=str(bot_id))
                    await _notify_admin(session, format_error(theme_name, "публикации", str(exc)))

    if published:
        logger.info("scheduler.publish_pool_done", published=published)


async def ad_watchdog_job() -> None:
    session_factory = get_session_factory()
    covered = 0
    async with session_factory() as session:
        result = await session.execute(
            select(AdDetection.id).where(AdDetection.action == AdDetectionAction.PENDING)
        )
        # Скаляры + re-get: commit/rollback per-detection экспайрит объекты.
        detection_ids = [det_id for (det_id,) in result.all()]

        for detection_id in detection_ids:
            try:
                detection = await session.get(AdDetection, detection_id)
                if detection is None:
                    continue
                target_channel = await session.get(TargetChannel, detection.target_channel_id)
                if target_channel is None:
                    continue
                theme_id = target_channel.theme_id
                target_title = target_channel.title
                channel_bot_result = await session.execute(
                    select(ChannelBot).where(
                        ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
                    )
                )
                channel_bot = channel_bot_result.scalar_one_or_none()
                if channel_bot is None:
                    continue

                async with Bot(token=channel_bot.bot_token) as bot:
                    if await cover_if_due(session, bot, detection_id):
                        covering_publication_id = detection.covering_publication_id
                        # Перекрытие уже отправлено в Telegram — фиксируем сразу,
                        # по той же причине, что в publish_pool_job.
                        await session.commit()
                        covered += 1
                        preview_text = ""
                        if covering_publication_id is not None:
                            publication = await session.get(Publication, covering_publication_id)
                            if publication is not None and publication.pool_post_id is not None:
                                pool_post = await session.get(PoolPost, publication.pool_post_id)
                                preview_text = pool_post.text if pool_post else ""
                        theme = await session.get(Theme, theme_id)
                        await _notify_admin(
                            session,
                            format_ad_covered(
                                AdCoveredNotification(
                                    theme_name=theme.name if theme else "",
                                    target_channel_title=target_title,
                                    covering_preview_text=preview_text,
                                )
                            ),
                        )
                    else:
                        # cover_if_due мог пометить детект IGNORED (например,
                        # разрешив гонку с собственной публикацией) — фиксируем.
                        await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "scheduler.ad_watchdog_detection_failed", detection_id=str(detection_id)
                )

    if covered:
        logger.info("scheduler.ad_watchdog_done", covered=covered)


async def _notify_admin(session, text: str) -> None:
    """Тихо no-op, если admin-бот не создан или ему ещё не написали /start
    (ChannelBot.notify_chat_id — см. interfaces/bots/handlers/admin_start.py) —
    отсутствие получателя не должно ронять сам job, уведомление это
    вторичный эффект, а не критичная часть пайплайна."""
    result = await session.execute(
        select(ChannelBot).where(ChannelBot.role == BotRole.ADMIN, ChannelBot.is_active.is_(True))
    )
    admin_bot = result.scalar_one_or_none()
    if admin_bot is None or admin_bot.notify_chat_id is None:
        return
    try:
        async with Bot(token=admin_bot.bot_token) as bot:
            await bot.send_message(admin_bot.notify_chat_id, text)
    except Exception:
        logger.exception("scheduler.admin_notify_failed")


async def _preview_text_for(session, next_post) -> str:
    if next_post.kind == "candidate":
        candidate = await session.get(CandidatePost, next_post.id)
        if candidate is None or candidate.selected_post_version_id is None:
            return ""
        post_version = await session.get(PostVersion, candidate.selected_post_version_id)
        return post_version.rewritten_text if post_version else ""

    pool_post = await session.get(PoolPost, next_post.id)
    return pool_post.text if pool_post else ""


async def _last_publication_at(session, target_channel_ids: list) -> datetime | None:
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
        heartbeat_job, "interval", seconds=HEARTBEAT_INTERVAL_SECONDS,
        id="heartbeat", max_instances=1,
    )
    scheduler.add_job(
        backfill_job, "interval", minutes=BACKFILL_INTERVAL_MINUTES,
        id="backfill", max_instances=1,
    )
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
