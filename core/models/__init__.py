"""Импорт всех моделей нужен, чтобы они зарегистрировались в Base.metadata —
это единственный источник для alembic autogenerate (migrations/env.py)."""

from core.models.ad_detection import AdDetection
from core.models.admin import Admin
from core.models.audit_log import AuditLog
from core.models.base import Base
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.metrics_snapshot import CandidateMetricsSnapshot, PublicationMetricsSnapshot
from core.models.panel_settings import PanelSettings
from core.models.pool_post import PoolPost
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.telethon_session import TelethonSession
from core.models.theme import Theme
from core.models.worker_heartbeat import WorkerHeartbeat

__all__ = [
    "Base",
    "Theme",
    "ChannelBot",
    "TelethonSession",
    "SourceChannel",
    "TargetChannel",
    "CandidatePost",
    "PostVersion",
    "CandidateMetricsSnapshot",
    "PublicationMetricsSnapshot",
    "PoolPost",
    "Publication",
    "AdDetection",
    "Admin",
    "AuditLog",
    "PanelSettings",
    "WorkerHeartbeat",
]
