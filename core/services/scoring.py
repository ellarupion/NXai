"""ScoringService — нормализованный скоринг чужих кандидатов по пересылкам
(см. ARCHITECTURE.md §5). Сырые forwards нечестно сравнивать между каналом на
5к подписчиков и на 500к — здесь score = forwards / медиана forwards канала
за последние 7 дней (fallback на сырые forwards, если истории меньше
MIN_SAMPLES_FOR_MEDIAN кандидатов — в первые дни работы source_channel
медиану считать не по чему).

Пост должен "дозреть": число пересылок за первые минуты почти всегда занижено
относительно итогового. CHECKPOINT_OFFSETS определяют контрольные точки
(+30 мин / +2 ч / +6 ч от first_seen_at), на которых core/services/ingest_candidates.py
дожидающиеся кандидаты подхватывает планировщик (см. ROADMAP.md Phase 1) и
переопрашивает через core/statistics/client.py.SourceStatsClient."""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.metrics_snapshot import CandidateMetricsSnapshot
from core.statistics.client import PostStats

logger = get_logger(__name__)

CHECKPOINT_OFFSETS = (timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
MIN_SAMPLES_FOR_MEDIAN = 5
# Порог отбора эвристический (см. ARCHITECTURE.md §5 — калибровка на реальных
# данных темы откладывается до Phase 1/2, как и HIGH_SIMILARITY_THRESHOLD в NX).
SELECTION_SCORE_THRESHOLD = 1.5


@dataclass(frozen=True)
class MaturationCheck:
    candidate_id: UUID
    next_checkpoint_due: bool


class ScoringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_snapshot(self, candidate_id: UUID, stats: PostStats, taken_at: datetime) -> float | None:
        """Сохраняет очередной снапшот и пересчитывает CandidatePost.score по
        последнему известному значению forwards. Возвращает новый score (None,
        если forwards ещё нет — например, канал скрыл счётчик)."""
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")

        self.session.add(
            CandidateMetricsSnapshot(
                candidate_post_id=candidate_id,
                views=stats.views,
                forwards=stats.forwards,
                taken_at=taken_at,
            )
        )

        if stats.forwards is None:
            await self.session.flush()
            return None

        median = await self._channel_median_forwards(candidate.source_channel_id, since_days=7)
        score = stats.forwards / median if median and median > 0 else float(stats.forwards)

        candidate.score = score
        if candidate.status is CandidatePostStatus.NEW:
            candidate.status = CandidatePostStatus.SCORING
        await self.session.flush()

        logger.info("scoring.snapshot_recorded", candidate_id=str(candidate_id), score=score)
        return score

    async def is_checkpoint_due(self, candidate: CandidatePost, now: datetime | None = None) -> bool:
        """True, если пришло время очередного контрольного переопроса метрик
        (см. CHECKPOINT_OFFSETS) и последний из них ещё не пройден."""
        now = now or datetime.now(timezone.utc)
        elapsed = now - candidate.first_seen_at
        return any(elapsed >= offset for offset in CHECKPOINT_OFFSETS) and candidate.status in (
            CandidatePostStatus.NEW,
            CandidatePostStatus.SCORING,
        )

    async def promote_if_selected(
        self, candidate_id: UUID, threshold: float = SELECTION_SCORE_THRESHOLD
    ) -> bool:
        """SCORING -> SELECTED, если последний score прошёл порог. Дедуп
        (core/services/dedup.py) должен отрабатывать ПОСЛЕ этого шага, а не до —
        дешёвый скоринг сначала отсеивает слабые посты, дорогой embedding-дедуп
        считается только для тех, что уже прошли порог (см. ARCHITECTURE.md §7:
        порядок шагов важен для стоимости)."""
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if candidate.score is None or candidate.score < threshold:
            return False

        candidate.status = CandidatePostStatus.SELECTED
        await self.session.flush()
        logger.info("scoring.selected", candidate_id=str(candidate_id), score=candidate.score)
        return True

    async def _channel_median_forwards(self, source_channel_id: UUID, since_days: int) -> float | None:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        # Последний снапшот на кандидата в окне — приближение "текущего" значения
        # forwards без отдельного подзапроса на MAX(taken_at); для MVP-объёма
        # кандидатов (десятки/сотни в день на тему) выборка в Python дешевле,
        # чем оконная функция в SQL, и проще для чтения.
        result = await self.session.execute(
            select(CandidateMetricsSnapshot.candidate_post_id, CandidateMetricsSnapshot.forwards)
            .join(CandidatePost, CandidatePost.id == CandidateMetricsSnapshot.candidate_post_id)
            .where(
                CandidatePost.source_channel_id == source_channel_id,
                CandidatePost.first_seen_at >= since,
                CandidateMetricsSnapshot.forwards.is_not(None),
            )
        )
        latest_by_candidate: dict[UUID, int] = {}
        for candidate_post_id, forwards in result.all():
            latest_by_candidate[candidate_post_id] = forwards

        values = list(latest_by_candidate.values())
        if len(values) < MIN_SAMPLES_FOR_MEDIAN:
            return None
        return statistics.median(values)
