import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from core.models.candidate_post import CandidatePost
    from core.models.telethon_session import TelethonSession
    from core.models.theme import Theme


class SourceChannel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Чужой публичный канал-источник, который читает Telethon-пул. В отличие
    от NX SourceChannel (свой приватный черновик-канал, куда бот добавлен
    админом), это канал, в котором мы никто — просто подписаны читающей
    Telethon-сессией. theme_id=NULL означает "ещё не распределён по теме" —
    такие каналы видны в панели в очереди на разбор (см. ARCHITECTURE.md §2:
    "в панели можно распределять какой канал к какому боту относится")."""

    __tablename__ = "source_channels"

    tg_username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))

    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ingest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("telethon_sessions.id", ondelete="SET NULL"), nullable=True
    )

    # Watermark для докачки истории при добавлении канала/после простоя ingest-воркера
    # (тот же принцип, что backfill в NX, но здесь это часть штатной работы, а не
    # ручная кнопка "Пересканировать" — см. ROADMAP.md Phase 1).
    last_scanned_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Множитель доверия к каналу при скоринге (core/services/scoring.py) — снижается
    # у источников, чьи кандидаты систематически проигрывают дедуп/помечаются низким
    # качеством в панели; см. ROADMAP.md Phase 5 ("вывод неэффективных source_channels").
    trust_score: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    theme: Mapped["Theme | None"] = relationship(back_populates="source_channels")
    ingest_session: Mapped["TelethonSession | None"] = relationship(back_populates="source_channels")
    candidate_posts: Mapped[list["CandidatePost"]] = relationship(back_populates="source_channel")
