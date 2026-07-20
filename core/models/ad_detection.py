import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import AdDetectionAction

if TYPE_CHECKING:
    from core.models.target_channel import TargetChannel


class AdDetection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Чужой (рекламный) пост, увиденный в СВОЁМ target_channel через
    channel_post-вебхук бота той темы — тот же принцип, что
    core/services/foreign_post.py в NX, но без шага ручного подтверждения:
    core/services/ad_watchdog.py сам форс-публикует пост из pool_posts темы
    через ~60 минут, если слот к этому времени не занят обычной публикацией
    (см. ARCHITECTURE.md §5)."""

    __tablename__ = "ad_detections"

    target_channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_channels.id", ondelete="CASCADE"), index=True
    )
    tg_message_id: Mapped[int] = mapped_column(BigInteger)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[AdDetectionAction] = mapped_column(default=AdDetectionAction.PENDING, index=True)
    covering_publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"), nullable=True
    )

    target_channel: Mapped["TargetChannel"] = relationship()
