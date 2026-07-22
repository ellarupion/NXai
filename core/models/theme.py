from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from core.models.channel_bot import ChannelBot
    from core.models.source_channel import SourceChannel
    from core.models.target_channel import TargetChannel


class Theme(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Тематическая ниша ("мужской", "женский", ...). Связывает воедино: набор
    чужих source_channels, которые панель к ней приписала, тематический
    ChannelBot (свой tg-токен и персона) и один или несколько TargetChannel,
    куда этот бот публикует."""

    __tablename__ = "themes"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    default_style_prompt: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # AI-дайджест (аудит, п.7.1): раз в сутки собрать топ виральных постов темы
    # за день в один авторский пост-дайджест → в очередь на одобрение. Формат,
    # который вообще не выглядит репостом. digest_hour — час в таймзоне проекта.
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    digest_hour: Mapped[int] = mapped_column(Integer, default=9, server_default="9")

    # Премодерация (UX-этап 3): рерайты темы идут в Проверку (PENDING_REVIEW),
    # автопаблиш публикует только одобренное. default=True — новые темы
    # премодерируемые (безопасный дефолт); server_default="false" — уже
    # существующие темы сохраняют прежнее поведение прямого автопаблиша.
    premoderation: Mapped[bool] = mapped_column(Boolean, default=True, server_default="false")

    source_channels: Mapped[list["SourceChannel"]] = relationship(back_populates="theme")
    target_channels: Mapped[list["TargetChannel"]] = relationship(back_populates="theme")
    bots: Mapped[list["ChannelBot"]] = relationship(back_populates="theme")
