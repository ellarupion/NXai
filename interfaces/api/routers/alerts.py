"""Алерты панели — просадка по теме, застой пула, источник без выхлопа,
пропущенные конфигурационные шаги (нет бота/целевого канала), забытые на
одобрении посты. Все проверки — чтение уже существующих таблиц, без
отдельного фонового job'а: считается на каждый запрос страницы, дёшево при
текущих объёмах (десятки тем/источников, не тысячи)."""

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
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.theme import Theme
from core.services.heartbeat import list_worker_status
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(get_current_admin)])

THEME_INACTIVITY_DAYS = 3
STALE_SOURCE_DAYS = 3
PENDING_REVIEW_STALE_HOURS = 24

_WORKER_LABELS = {
    "scheduler": "Планировщик (публикация, скоринг, дедуп)",
    "ingest": "Читалка чужих каналов (Telethon)",
    "bots": "Боты (публикация, ad watchdog)",
}


class Alert(BaseModel):
    severity: str  # "warning" | "info"
    category: str
    message: str
    theme_id: UUID | None = None
    source_channel_id: UUID | None = None


@router.get("", response_model=list[Alert])
async def list_alerts(session: AsyncSession = Depends(get_db)) -> list[Alert]:
    now = datetime.now(timezone.utc)
    alerts: list[Alert] = []

    themes_result = await session.execute(select(Theme).where(Theme.is_active.is_(True)))
    themes = list(themes_result.scalars().all())

    for theme in themes:
        bot = await session.scalar(
            select(ChannelBot).where(
                ChannelBot.theme_id == theme.id,
                ChannelBot.role == BotRole.THEME,
                ChannelBot.is_active.is_(True),
            )
        )
        if bot is None:
            alerts.append(
                Alert(
                    severity="warning",
                    category="missing_bot",
                    message=f"У темы «{theme.name}» нет активного бота",
                    theme_id=theme.id,
                )
            )

        target_count = await session.scalar(
            select(func.count())
            .select_from(TargetChannel)
            .where(TargetChannel.theme_id == theme.id, TargetChannel.is_active.is_(True))
        )
        if not target_count:
            alerts.append(
                Alert(
                    severity="warning",
                    category="missing_target_channel",
                    message=f"У темы «{theme.name}» нет активного целевого канала",
                    theme_id=theme.id,
                )
            )
        else:
            since = now - timedelta(days=THEME_INACTIVITY_DAYS)
            last_published_at = await session.scalar(
                select(func.max(Publication.published_at))
                .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
                .where(TargetChannel.theme_id == theme.id)
            )
            if last_published_at is None or last_published_at < since:
                alerts.append(
                    Alert(
                        severity="warning",
                        category="theme_inactive",
                        message=(
                            f"Тема «{theme.name}» не публиковалась последние "
                            f"{THEME_INACTIVITY_DAYS} дн."
                        ),
                        theme_id=theme.id,
                    )
                )

        ready_pool_count = await session.scalar(
            select(func.count())
            .select_from(PoolPost)
            .where(PoolPost.theme_id == theme.id, PoolPost.status == PoolPostStatus.READY)
        )
        if not ready_pool_count:
            alerts.append(
                Alert(
                    severity="info",
                    category="pool_stagnant",
                    message=(
                        f"У темы «{theme.name}» нет готовых постов в пуле — ad watchdog "
                        "не сможет перекрыть рекламу"
                    ),
                    theme_id=theme.id,
                )
            )

    stale_since = now - timedelta(days=STALE_SOURCE_DAYS)
    sources_result = await session.execute(
        select(SourceChannel).where(
            SourceChannel.is_active.is_(True), SourceChannel.ingest_session_id.is_not(None)
        )
    )
    for source_channel in sources_result.scalars().all():
        recent_candidate_count = await session.scalar(
            select(func.count())
            .select_from(CandidatePost)
            .where(
                CandidatePost.source_channel_id == source_channel.id,
                CandidatePost.first_seen_at >= stale_since,
            )
        )
        never_or_stale_scan = (
            source_channel.last_scanned_at is None or source_channel.last_scanned_at < stale_since
        )
        if not recent_candidate_count and never_or_stale_scan:
            alerts.append(
                Alert(
                    severity="info",
                    category="source_no_output",
                    message=(
                        f"Источник «{source_channel.title}» не дал ни одного поста за "
                        f"{STALE_SOURCE_DAYS} дн."
                    ),
                    source_channel_id=source_channel.id,
                )
            )

    stale_review_since = now - timedelta(hours=PENDING_REVIEW_STALE_HOURS)
    stale_pending_result = await session.execute(
        select(SourceChannel.theme_id, func.count())
        .select_from(CandidatePost)
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(
            CandidatePost.status == CandidatePostStatus.PENDING_REVIEW,
            CandidatePost.created_at < stale_review_since,
        )
        .group_by(SourceChannel.theme_id)
    )
    for theme_id, count in stale_pending_result.all():
        if theme_id is None:
            continue
        theme = await session.get(Theme, theme_id)
        alerts.append(
            Alert(
                severity="info",
                category="pending_review_stale",
                message=(
                    f"{count} пост(ов) темы «{theme.name if theme else theme_id}» ждут "
                    f"одобрения больше {PENDING_REVIEW_STALE_HOURS} ч."
                ),
                theme_id=theme_id,
            )
        )

    # Живость фоновых процессов (аудит, п.3.1): остальные алерты видят проблемы
    # в данных/конфигурации, но не заметят, что сам scheduler/ingest/bots упал
    # или завис — это ловит heartbeat.
    for status in await list_worker_status(session, now):
        if status["is_alive"]:
            continue
        label = _WORKER_LABELS.get(status["worker_name"], status["worker_name"])
        if status["last_beat_at"] is None:
            message = f"Процесс «{label}» ни разу не выходил на связь — он запущен?"
        else:
            message = f"Процесс «{label}» не отвечает — последний сигнал был давно, вероятно упал или завис"
        alerts.append(Alert(severity="warning", category="worker_down", message=message))

    return alerts
