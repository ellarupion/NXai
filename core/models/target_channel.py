import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from core.models.theme import Theme


class TargetChannel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Канал публикации одной темы — бот (ChannelBot той же theme_id) должен
    быть в нём админом (иначе не работает ни публикация, ни детект чужих/
    рекламных постов через channel_post-вебхук, см. core/services/ad_watchdog.py).
    "Убрать" канал — is_active=False, не удаление строки (сохраняем историю
    publications)."""

    __tablename__ = "target_channels"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="CASCADE"), index=True
    )
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    signature: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    theme: Mapped["Theme"] = relationship(back_populates="target_channels")
