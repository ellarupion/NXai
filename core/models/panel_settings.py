from sqlalchemy import LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PanelSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton-строка (first-row-or-create, как в NX) — брендинг панели и
    secret-override для ключей, общих для всего процесса. В отличие от NX
    здесь НЕТ per-bot токенов (bot_token_override и т.п.) — токен каждого
    тематического/admin-бота живёт в core/models/channel_bot.py, потому что
    ботов много и они создаются из панели, а не фиксированы в .env/singleton."""

    __tablename__ = "panel_settings"

    panel_title: Mapped[str] = mapped_column(String(255), default="NXai")
    accent_color: Mapped[str] = mapped_column(String(16), default="#5B8DEF")
    logo_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    anthropic_api_key_override: Mapped[str] = mapped_column(Text, default="")
    voyage_api_key_override: Mapped[str] = mapped_column(Text, default="")
