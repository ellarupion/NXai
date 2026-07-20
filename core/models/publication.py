import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import PublicationSource

if TYPE_CHECKING:
    from core.models.target_channel import TargetChannel


class Publication(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Факт публикации в целевой канал — либо рерайт кандидата
    (source=CANDIDATE, post_version_id заполнен), либо пост из собственного
    пула (source=POOL, pool_post_id заполнен; is_ad_cover=True, если это было
    автоматическое перекрытие рекламы — core/services/ad_watchdog.py). Ровно
    одно из post_version_id/pool_post_id должно быть заполнено — проверяется
    в сервисном слое (core/services/publisher.py), не на уровне БД."""

    __tablename__ = "publications"

    target_channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_channels.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[PublicationSource] = mapped_column()
    post_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("post_versions.id", ondelete="SET NULL"), nullable=True
    )
    pool_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pool_posts.id", ondelete="SET NULL"), nullable=True
    )
    tg_message_id: Mapped[int] = mapped_column(BigInteger)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_ad_cover: Mapped[bool] = mapped_column(Boolean, default=False)

    target_channel: Mapped["TargetChannel"] = relationship()
