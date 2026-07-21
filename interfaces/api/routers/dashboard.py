"""Агрегированная статистика для дашборда — чистые COUNT/GROUP BY по уже
существующим таблицам, без похода в Telegram (живой сбор
views/forwards/engagement публикаций — core/services/analytics.py, требует
выделенной Telethon-сессии в целевых каналах и отдельного scheduler-job,
ROADMAP.md Phase 5, здесь не реализовано)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus, PoolPostStatus
from core.models.pool_post import PoolPost
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.theme import Theme
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_admin)])


class TopSourceOut(BaseModel):
    title: str
    candidate_count: int


class DashboardStatsOut(BaseModel):
    themes_total: int
    themes_active: int
    source_channels_total: int
    source_channels_unassigned: int
    candidates_by_status: dict[str, int]
    pending_review_count: int
    publications_total: int
    publications_today: int
    pool_posts_total: int
    pool_posts_ready: int
    top_sources: list[TopSourceOut]


@router.get("/stats", response_model=DashboardStatsOut)
async def get_dashboard_stats(session: AsyncSession = Depends(get_db)) -> DashboardStatsOut:
    themes_total = await session.scalar(select(func.count()).select_from(Theme)) or 0
    themes_active = await session.scalar(
        select(func.count()).select_from(Theme).where(Theme.is_active.is_(True))
    ) or 0

    source_channels_total = await session.scalar(select(func.count()).select_from(SourceChannel)) or 0
    source_channels_unassigned = await session.scalar(
        select(func.count()).select_from(SourceChannel).where(SourceChannel.theme_id.is_(None))
    ) or 0

    status_rows = await session.execute(
        select(CandidatePost.status, func.count()).group_by(CandidatePost.status)
    )
    candidates_by_status = {status.value: count for status, count in status_rows.all()}
    # Нули явно для статусов без единой записи — панели проще рисовать
    # стабильный набор плиток, чем проверять наличие ключа.
    for status in CandidatePostStatus:
        candidates_by_status.setdefault(status.value, 0)

    pending_review_count = candidates_by_status.get(CandidatePostStatus.PENDING_REVIEW.value, 0)

    publications_total = await session.scalar(select(func.count()).select_from(Publication)) or 0
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    publications_today = await session.scalar(
        select(func.count()).select_from(Publication).where(Publication.published_at >= today_start)
    ) or 0

    pool_posts_total = await session.scalar(select(func.count()).select_from(PoolPost)) or 0
    pool_posts_ready = await session.scalar(
        select(func.count()).select_from(PoolPost).where(PoolPost.status == PoolPostStatus.READY)
    ) or 0

    top_sources_result = await session.execute(
        select(SourceChannel.title, func.count(CandidatePost.id).label("candidate_count"))
        .join(CandidatePost, CandidatePost.source_channel_id == SourceChannel.id)
        .group_by(SourceChannel.id, SourceChannel.title)
        .order_by(func.count(CandidatePost.id).desc())
        .limit(5)
    )
    top_sources = [
        TopSourceOut(title=title, candidate_count=count) for title, count in top_sources_result.all()
    ]

    return DashboardStatsOut(
        themes_total=themes_total,
        themes_active=themes_active,
        source_channels_total=source_channels_total,
        source_channels_unassigned=source_channels_unassigned,
        candidates_by_status=candidates_by_status,
        pending_review_count=pending_review_count,
        publications_total=publications_total,
        publications_today=publications_today,
        pool_posts_total=pool_posts_total,
        pool_posts_ready=pool_posts_ready,
        top_sources=top_sources,
    )
