import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import BotRole

if TYPE_CHECKING:
    from core.models.theme import Theme

DEFAULT_CADENCE = {
    "posts_per_day_target": 8,
    "min_interval_minutes": 30,
    "max_interval_minutes": 180,
    "jitter_minutes": 15,
    "quiet_hours_start": 23,
    "quiet_hours_end": 8,
}


class ChannelBot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Один Telegram-бот (свой BotFather-токен) — либо публикующий бот одной
    темы (role=THEME, theme_id обязателен), либо единственный агрегирующий
    admin-бот (role=ADMIN, theme_id=NULL). В отличие от NX, где было ровно два
    фиксированных токена (editor + submission) из .env, здесь число ботов
    растёт из панели вместе с числом тем — поэтому токен хранится в БД, а не
    в Settings, и шифруется на уровне сервиса, который его читает/пишет
    (core/services/admin_notify.py и слой панели), а не здесь в модели.

    cadence — JSONB (см. DEFAULT_CADENCE): каданс публикации из пула для
    этой темы, используется core/services/scheduler_pool.py (шафл + джиттер,
    см. ARCHITECTURE.md §5). Для role=ADMIN не используется."""

    __tablename__ = "channel_bots"

    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[BotRole] = mapped_column(default=BotRole.THEME, index=True)
    bot_token: Mapped[str] = mapped_column(Text)
    persona_prompt: Mapped[str] = mapped_column(Text, default="")
    cadence: Mapped[dict] = mapped_column(JSONB, default=DEFAULT_CADENCE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    theme: Mapped["Theme | None"] = relationship(back_populates="bots")
