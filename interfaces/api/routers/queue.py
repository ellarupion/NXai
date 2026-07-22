"""Очередь публикаций (UX-этап 6): прогноз «что и когда выйдет» по каждой
активной теме. Точных времён у автопаблиша нет по замыслу (шафл + джиттер,
core/services/scheduler_pool.py), поэтому прогноз строится по среднему
интервалу расписания бота с учётом тихих часов — панель честно называет
слоты ориентировочными."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole, CandidatePostStatus, PoolPostStatus
from core.models.pool_post import PoolPost
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.theme import Theme
from core.services.panel_settings import get_or_create_panel_settings
from core.services.scheduler_pool import is_quiet_hour, resolve_zoneinfo
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/queue", tags=["queue"], dependencies=[Depends(get_current_admin)])

FORECAST_HOURS = 48
MAX_SLOTS = 16


class RecentPublication(BaseModel):
    published_at: datetime
    channel_title: str
    preview: str


class ThemeQueueOut(BaseModel):
    theme_id: UUID
    theme_name: str
    has_active_bot: bool
    ready_posts: int
    pool_ready: int
    posts_per_day: int
    # Сколько дней контента осталось при текущем темпе; None — публиковать
    # некому (нет активного бота).
    days_left: float | None
    # Ориентировочные времена ближайших публикаций (UTC).
    next_slots: list[datetime]
    recent: list[RecentPublication]


class QueueForecastOut(BaseModel):
    themes: list[ThemeQueueOut]


def _forecast_slots(
    cadence: dict, last_published_at: datetime | None, available: int, now: datetime, tz
) -> list[datetime]:
    """Слоты по среднему интервалу расписания, тихие часы пропускаются
    (сдвигаем слот вперёд почасово до выхода из тишины). Без random —
    прогноз должен быть стабильным между запросами."""
    if available <= 0:
        return []
    avg_minutes = (cadence["min_interval_minutes"] + cadence["max_interval_minutes"]) / 2
    step = timedelta(minutes=max(avg_minutes, 1))
    horizon = now + timedelta(hours=FORECAST_HOURS)

    cursor = now
    if last_published_at is not None:
        min_next = last_published_at + timedelta(minutes=cadence["min_interval_minutes"])
        cursor = max(cursor, min_next)

    slots: list[datetime] = []
    while cursor <= horizon and len(slots) < min(available, MAX_SLOTS):
        shifted = cursor
        guard = 0
        while is_quiet_hour(cadence, shifted, tz) and guard < 24:
            shifted += timedelta(hours=1)
            shifted = shifted.replace(minute=cursor.minute)
            guard += 1
        if shifted > horizon:
            break
        slots.append(shifted)
        cursor = shifted + step
    return slots


@router.get("/forecast", response_model=QueueForecastOut)
async def queue_forecast(session: AsyncSession = Depends(get_db)) -> QueueForecastOut:
    now = datetime.now(timezone.utc)
    panel_settings = await get_or_create_panel_settings(session)
    tz = resolve_zoneinfo(panel_settings.timezone)

    themes_result = await session.execute(
        select(Theme).where(Theme.is_active.is_(True)).order_by(Theme.name)
    )
    out: list[ThemeQueueOut] = []
    for theme in themes_result.scalars().all():
        bot = await session.scalar(
            select(ChannelBot).where(
                ChannelBot.theme_id == theme.id,
                ChannelBot.role == BotRole.THEME,
                ChannelBot.is_active.is_(True),
            )
        )
        ready_posts = await session.scalar(
            select(func.count())
            .select_from(CandidatePost)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                SourceChannel.theme_id == theme.id,
                CandidatePost.status == CandidatePostStatus.REWRITTEN,
            )
        )
        pool_ready = await session.scalar(
            select(func.count())
            .select_from(PoolPost)
            .where(PoolPost.theme_id == theme.id, PoolPost.status == PoolPostStatus.READY)
        )
        last_published_at = await session.scalar(
            select(func.max(Publication.published_at))
            .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
            .where(TargetChannel.theme_id == theme.id)
        )

        # Текст публикации живёт в PostVersion (рерайты) или PoolPost (запас) —
        # outerjoin к обоим, берём что есть.
        recent_result = await session.execute(
            select(
                Publication.published_at,
                TargetChannel.title,
                PostVersion.rewritten_text,
                PoolPost.text,
            )
            .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
            .outerjoin(PostVersion, PostVersion.id == Publication.post_version_id)
            .outerjoin(PoolPost, PoolPost.id == Publication.pool_post_id)
            .where(TargetChannel.theme_id == theme.id)
            .order_by(Publication.published_at.desc())
            .limit(5)
        )
        recent = [
            RecentPublication(
                published_at=published_at,
                channel_title=title,
                preview=((rewritten or pool_text or ""))[:120],
            )
            for published_at, title, rewritten, pool_text in recent_result.all()
        ]

        available = (ready_posts or 0) + (pool_ready or 0)
        if bot is None:
            out.append(
                ThemeQueueOut(
                    theme_id=theme.id,
                    theme_name=theme.name,
                    has_active_bot=False,
                    ready_posts=ready_posts or 0,
                    pool_ready=pool_ready or 0,
                    posts_per_day=0,
                    days_left=None,
                    next_slots=[],
                    recent=recent,
                )
            )
            continue

        posts_per_day = int(bot.cadence.get("posts_per_day_target") or 0)
        days_left = round(available / posts_per_day, 1) if posts_per_day else None
        out.append(
            ThemeQueueOut(
                theme_id=theme.id,
                theme_name=theme.name,
                has_active_bot=True,
                ready_posts=ready_posts or 0,
                pool_ready=pool_ready or 0,
                posts_per_day=posts_per_day,
                days_left=days_left,
                next_slots=_forecast_slots(bot.cadence, last_published_at, available, now, tz),
                recent=recent,
            )
        )

    return QueueForecastOut(themes=out)
