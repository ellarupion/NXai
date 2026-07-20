from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import AuditAction


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Неизменяемый журнал действий — перенесено из NX без изменений в форме,
    набор actor_tg_user_id=NULL/0 по-прежнему значит "система" (автоматика
    пайплайна, а не ручное действие оператора)."""

    __tablename__ = "audit_logs"

    actor_tg_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[AuditAction] = mapped_column(index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
