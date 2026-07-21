from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.types import EncryptedText

if TYPE_CHECKING:
    from core.models.source_channel import SourceChannel


class TelethonSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Один аккаунт из пула Telethon-читалок (см. ARCHITECTURE.md §7: одна
    user-сессия надёжно держит ограниченное число каналов, поэтому источники
    шардируются по нескольким сессиям, а не по одной раздутой). session_string
    генерируется веб-логином (core/services/telethon_login.py) или одноразовым
    скриптом (scripts/generate_telethon_session.py) и хранится зашифрованным —
    тип EncryptedText (core/models/types.py, шифрование core/crypto.py); наружу
    через API не отдаётся и не логируется.

    Только на чтение: core/services/ingest_candidates.py вызывает
    events.NewMessage/iter_messages, никогда не пишет/не публикует от имени
    этого аккаунта."""

    __tablename__ = "telethon_sessions"

    label: Mapped[str] = mapped_column(String(255))
    session_string: Mapped[str] = mapped_column(EncryptedText)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    source_channels: Mapped[list["SourceChannel"]] = relationship(back_populates="ingest_session")
