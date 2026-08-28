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
from core.services.automation import AutomationSettings, get_automation
from core.models.metrics_snapshot import CandidateMetricsSnapshot
from core.models.source_channel import SourceChannel
from core.statistics.client import PostStats

logger = get_logger(__name__)

CHECKPOINT_OFFSETS = (timedelta(minutes=30), timedelta(hours=2), timedelta(hours=6))
MAX_CHECKPOINT_OFFSET = max(CHECKPOINT_OFFSETS)
# Порог отбора и минимум выборки для медианы переехали в настройки панели
# (core/services/automation.py): это самые влиятельные числа в системе, и менять их
# пересборкой образа — ровно та ситуация, из-за которой тема однажды замолчала
# на недели.


@dataclass(frozen=True)
class MaturationCheck:
    candidate_id: UUID
    next_checkpoint_due: bool


class ScoringService:
    def __init__(self, session: AsyncSession, automation: AutomationSettings | None = None) -> None:
        self.session = session
        # Настройки читаем один раз и лениво: сервис создаётся на тик планировщика и
        # обрабатывает десятки кандидатов — ходить в базу за порогом на каждого незачем.
        self._automation = automation

    async def automation(self) -> AutomationSettings:
        if self._automation is None:
            self._automation = await get_automation(self.session)
        return self._automation

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

        # trust_score — множитель (core/services/trust_score.py): источник,
        # систематически дающий дубли/отклонённые посты, должен показать
        # пропорционально более высокий сырой score, чтобы всё равно пройти
        # порог отбора — без этого trust_score был бы просто цифрой в API,
        # ни на что не влияющей.
        source_channel = await self.session.get(SourceChannel, candidate.source_channel_id)
        if source_channel is not None:
            score *= source_channel.trust_score

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

    async def promote_if_selected(self, candidate_id: UUID, threshold: float | None = None) -> bool:
        """SCORING -> SELECTED, если последний score прошёл порог. Дедуп
        (core/services/dedup.py) должен отрабатывать ПОСЛЕ этого шага, а не до —
        дешёвый скоринг сначала отсеивает слабые посты, дорогой embedding-дедуп
        считается только для тех, что уже прошли порог (см. ARCHITECTURE.md §7:
        порядок шагов важен для стоимости)."""
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if threshold is None:
            threshold = (await self.automation()).selection_score_threshold
        if candidate.score is None or candidate.score < threshold:
            return False

        candidate.status = CandidatePostStatus.SELECTED
        await self.session.flush()
        logger.info("scoring.selected", candidate_id=str(candidate_id), score=candidate.score)
        return True

    async def reject_if_matured(self, candidate: CandidatePost, now: datetime | None = None) -> bool:
        """Кандидат, доживший до последней контрольной точки (+6ч) и так и не
        прошедший promote_if_selected — is_checkpoint_due() больше никогда не
        подхватит его повторно (статус остался NEW/SCORING, но все офсеты уже
        пройдены), поэтому без этого он завис бы в SCORING навсегда. Закрываем
        явно как REJECTED и слегка снижаем доверие к источнику."""
        now = now or datetime.now(timezone.utc)
        if candidate.status not in (CandidatePostStatus.NEW, CandidatePostStatus.SCORING):
            return False
        if now - candidate.first_seen_at < MAX_CHECKPOINT_OFFSET:
            return False

        candidate.status = CandidatePostStatus.REJECTED
        await self.session.flush()
        # ВАЖНО: здесь НЕТ штрафа доверия, и это не упущение.
        #
        # Раньше стоял adjust_trust_score(-REJECTED_PENALTY), и это замыкало
        # систему саму на себя. Порог отбора нормирован по медиане канала, то
        # есть большинство постов не проходит его ПО ПОСТРОЕНИЮ — половина
        # постов канала по определению ниже его же медианы. Штрафуя источник за
        # каждый такой пост, мы штрафовали его за нормальную статистику: от 1.0
        # до нижней границы 0.1 хватало 18 отклонений. А дальше score умножался
        # на 0.1, и чтобы пройти порог 1.5, посту требовалось 15 медиан канала —
        # недостижимо. Источник замолкал навсегда, и по этой петле легла вся
        # система: 5171 отклонение подряд при 22 публикациях.
        #
        # Доверие теперь снижают только осмысленные сигналы: РУЧНОЕ отклонение
        # оператором (core/services/review.py — «этот пост плохой») и дубли
        # (core/services/dedup.py — «источник повторяет чужое»). Не пройти
        # порог виральности — это штатный исход, а не претензия к источнику.
        logger.info("scoring.rejected_matured", candidate_id=str(candidate.id), score=candidate.score)
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
        if len(values) < (await self.automation()).min_samples_for_median:
            return None
        return statistics.median(values)
