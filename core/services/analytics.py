"""AnalyticsService — сбор метрик СВОИХ публикаций и агрегация для дашборда/
admin-бота (адаптировано из NX core/services/analytics.py). В отличие от NX,
метрики хранятся как временной ряд (PublicationMetricsSnapshot), а не как
последнее значение в JSONB — см. core/models/metrics_snapshot.py.

Просмотры/пересылки читаются через core/statistics/client.py.SourceStatsClient
(тот же Telethon-пул, что используется для скоринга чужих кандидатов — сессия
должна быть участником и целевых каналов тоже, не только источников);
реакции — через message_reaction_count из Bot API, как в NX."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.metrics_snapshot import PublicationMetricsSnapshot
from core.models.publication import Publication
from core.models.target_channel import TargetChannel
from core.statistics.client import SourceStatsClient

logger = get_logger(__name__)


@dataclass(frozen=True)
class TopPost:
    publication_id: UUID
    target_channel_title: str
    forwards: int
    views: int | None


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def collect_metrics_for_publication(
        self, stats_client: SourceStatsClient, publication_id: UUID
    ) -> None:
        publication = await self.session.get(Publication, publication_id)
        if publication is None:
            raise ValueError(f"Publication {publication_id} not found")

        target_channel = await self.session.get(TargetChannel, publication.target_channel_id)
        if target_channel is None:
            raise ValueError(f"TargetChannel {publication.target_channel_id} not found")

        stats = await stats_client.get_post_stats(target_channel.tg_chat_id, publication.tg_message_id)
        if stats is None:
            logger.warning("analytics.post_not_found", publication_id=str(publication_id))
            return

        self.session.add(
            PublicationMetricsSnapshot(
                publication_id=publication_id,
                views=stats.views,
                forwards=stats.forwards,
                taken_at=datetime.now(timezone.utc),
            )
        )
        await self.session.flush()

    async def collect_recent_metrics(self, stats_client: SourceStatsClient, within_days: int = 7) -> int:
        since = datetime.now(timezone.utc) - timedelta(days=within_days)
        result = await self.session.execute(
            select(Publication.id).where(Publication.published_at >= since)
        )
        publication_ids = [row[0] for row in result.all()]

        collected = 0
        for publication_id in publication_ids:
            try:
                await self.collect_metrics_for_publication(stats_client, publication_id)
                collected += 1
            except Exception:
                logger.exception("analytics.collect_failed", publication_id=str(publication_id))
        return collected

    async def top_posts_by_forwards(self, theme_id: UUID, within_days: int = 7, limit: int = 5) -> list[TopPost]:
        """Ранжирование по пересылкам, а не по просмотрам — тот же продуктовый
        выбор, что в NX (core/services/analytics.py.DashboardService._top_posts),
        здесь по последнему снапшоту на публикацию, а не единственному JSONB-значению."""
        since = datetime.now(timezone.utc) - timedelta(days=within_days)
        result = await self.session.execute(
            select(Publication, TargetChannel, PublicationMetricsSnapshot)
            .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
            .join(PublicationMetricsSnapshot, PublicationMetricsSnapshot.publication_id == Publication.id)
            .where(
                TargetChannel.theme_id == theme_id,
                Publication.published_at >= since,
                PublicationMetricsSnapshot.forwards.is_not(None),
            )
            .order_by(PublicationMetricsSnapshot.taken_at.desc())
        )
        latest_by_publication: dict[UUID, TopPost] = {}
        for publication, target_channel, snapshot in result.all():
            if publication.id in latest_by_publication:
                continue
            latest_by_publication[publication.id] = TopPost(
                publication_id=publication.id,
                target_channel_title=target_channel.title,
                forwards=snapshot.forwards,
                views=snapshot.views,
            )

        top = sorted(latest_by_publication.values(), key=lambda p: p.forwards, reverse=True)
        return top[:limit]


def engagement_rate(views: int | None, reactions: int | None, forwards: int | None) -> float | None:
    """(реакции + пересылки) / просмотры — та же формула, что в NX
    core/services/analytics.py.engagement_rate, переиспользуется во всех
    отчётах/дашбордах, чтобы формулы не расходились между страницами панели."""
    if not views:
        return None
    return ((reactions or 0) + (forwards or 0)) / views
