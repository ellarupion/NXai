"""SchedulerPoolService — шафл порядка выхода и джиттер времени публикации
(см. ARCHITECTURE.md §5). В отличие от NX PublisherService.run_due_publications
(строгий FIFO по явному Draft.scheduled_for, выставленному вручную), здесь нет
предзаданного времени публикации на кандидата — планировщик на каждом тике
решает, пора ли публиковать (is_due) и что публиковать (pick_next),
взвешенно-случайно по score, а не по порядку появления в источниках."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus, PoolPostStatus
from core.models.pool_post import PoolPost
from core.models.source_channel import SourceChannel

logger = get_logger(__name__)

DEFAULT_TIMEZONE = "Europe/Moscow"


def resolve_zoneinfo(tz_name: str | None) -> ZoneInfo:
    """Безопасно превращает строку-таймзону из панели в ZoneInfo; при опечатке/
    отсутствии базы tzdata откатывается на дефолт, а не роняет весь тик
    публикации из-за одной неверной настройки."""
    try:
        return ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("scheduler_pool.bad_timezone", tz_name=tz_name)
        return ZoneInfo(DEFAULT_TIMEZONE)


def is_quiet_hour(cadence: dict, at: datetime, tz: ZoneInfo | None = None) -> bool:
    """`at` приводится к таймзоне проекта перед сравнением часа: quiet_hours
    задаются настенными часами оператора, а `at` приходит в UTC (аудит, К3).
    tz=None сохраняет старое поведение (сравнение по UTC) для обратной
    совместимости вызовов без зоны."""
    local = at.astimezone(tz) if tz is not None else at
    start, end = cadence["quiet_hours_start"], cadence["quiet_hours_end"]
    hour = local.hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def is_due(
    cadence: dict,
    last_published_at: datetime | None,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
) -> bool:
    """Пора ли публиковать: не в тихие часы (в таймзоне проекта), и прошло не
    меньше min_interval_minutes с последней публикации темы (max_interval_minutes —
    ориентир для планирования джиттера в next_allowed_delay, здесь не проверяется
    напрямую — если тик планировщика реже max_interval, важнее не публиковать
    слишком часто, чем строго уложиться в максимум)."""
    now = now or datetime.now(timezone.utc)
    if is_quiet_hour(cadence, now, tz):
        return False
    if last_published_at is None:
        return True
    min_interval = timedelta(minutes=cadence["min_interval_minutes"])
    return now - last_published_at >= min_interval


def next_allowed_delay(cadence: dict) -> timedelta:
    """Случайный интервал до следующей публикации в пределах [min, max] +
    джиттер — используется, если планировщику нужно заранее оценить следующий
    слот (например, при первом запуске темы), а не только проверять is_due
    на каждый тик."""
    base_minutes = random.uniform(cadence["min_interval_minutes"], cadence["max_interval_minutes"])
    jitter_minutes = random.uniform(-cadence["jitter_minutes"], cadence["jitter_minutes"])
    return timedelta(minutes=max(1.0, base_minutes + jitter_minutes))


@dataclass(frozen=True)
class NextPost:
    kind: str  # "candidate" | "pool"
    id: UUID


class SchedulerPoolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def pick_next(self, theme_id: UUID, pool_cooldown_days: int = 0) -> NextPost | None:
        """REWRITTEN-кандидаты темы в приоритете (взвешенно-случайно по score —
        не всегда самый "вирусный", чтобы порядок выхода не был предсказуемым),
        pool_posts — fallback, когда пул рерайтов пуст (см. ARCHITECTURE.md §5).
        pool_cooldown_days ограничивает переиспользование пула (аудит, п.3.3)."""
        candidate = await self._pick_weighted_candidate(theme_id)
        if candidate is not None:
            return NextPost(kind="candidate", id=candidate.id)

        pool_post = await self.pick_pool_post(theme_id, pool_cooldown_days=pool_cooldown_days)
        if pool_post is not None:
            return NextPost(kind="pool", id=pool_post.id)

        return None

    async def _pick_weighted_candidate(self, theme_id: UUID) -> CandidatePost | None:
        result = await self.session.execute(
            select(CandidatePost)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                CandidatePost.status == CandidatePostStatus.REWRITTEN,
                SourceChannel.theme_id == theme_id,
            )
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        weights = [max(c.score or 0.0, 0.01) for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    async def pick_pool_post(
        self,
        theme_id: UUID,
        pool_cooldown_days: int = 0,
        allow_repeat_when_all_on_cooldown: bool = True,
    ) -> PoolPost | None:
        """Берёт наименее недавно использованный READY-пост темы. При
        pool_cooldown_days > 0 исключает посты, публиковавшиеся за последние
        N дней (аудит, п.3.3).

        allow_repeat_when_all_on_cooldown: если все посты на кулдауне —
        True (по умолчанию, для ad-cover) повторяет наименее недавний, чтобы
        не оставить рекламу неперекрытой; False (обычное заполнение расписания
        из pick_next) возвращает None — пусть слот пропустится, чем выйдет
        повтор раньше срока."""
        base = (
            select(PoolPost)
            .where(PoolPost.theme_id == theme_id, PoolPost.status == PoolPostStatus.READY)
            .order_by(PoolPost.last_used_at.asc().nulls_first())
        )
        if pool_cooldown_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=pool_cooldown_days)
            fresh = await self.session.execute(
                base.where(
                    (PoolPost.last_used_at.is_(None)) | (PoolPost.last_used_at < cutoff)
                ).limit(1)
            )
            picked = fresh.scalar_one_or_none()
            if picked is not None:
                return picked
            if not allow_repeat_when_all_on_cooldown:
                return None
        result = await self.session.execute(base.limit(1))
        return result.scalar_one_or_none()


__all__ = ["SchedulerPoolService", "NextPost", "is_due", "is_quiet_hour", "next_allowed_delay"]
