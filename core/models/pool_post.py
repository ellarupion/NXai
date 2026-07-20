import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import PoolPostSource, PoolPostStatus

if TYPE_CHECKING:
    from core.models.theme import Theme


class PoolPost(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Собственный запасной пул темы — evergreen-контент, не привязанный к
    конкретному чужому кандидату. Используется в двух ролях (см.
    ARCHITECTURE.md §5): обычное заполнение расписания, когда пул
    REWRITTEN-кандидатов пуст, и авто-перекрытие рекламных постов
    (core/services/ad_watchdog.py). times_used растёт при каждой публикации —
    в отличие от candidate_posts, один pool_post можно использовать
    повторно, поэтому статус после публикации возвращается в READY, а не
    становится терминальным."""

    __tablename__ = "pool_posts"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[PoolPostSource] = mapped_column(default=PoolPostSource.MANUAL)
    status: Mapped[PoolPostStatus] = mapped_column(default=PoolPostStatus.READY, index=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    theme: Mapped["Theme"] = relationship()
