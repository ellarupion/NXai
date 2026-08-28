import uuid

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import AuditAction


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Неизменяемый журнал действий.

    Раньше он писался, но прочитать его было нечем: эндпоинта и страницы не было, и
    таблица просто росла. Плюс запись не помнила ни кто действовал, ни откуда, ни в
    какой теме — на вопрос «кто одобрил этот пост» ответа не было.

    Два способа назвать автора, потому что их два и они разные. В панель входят по
    логину и паролю (actor_admin_username), в ботах человек известен только своим
    telegram-идентификатором (actor_tg_user_id). Оба пустые — действие системное:
    планировщик, приём постов, автоматическое перекрытие рекламы.
    """

    __tablename__ = "audit_logs"
    # Индекс по дате: журнал читают лентой «последние сверху», и без него выборка
    # сканировала бы таблицу целиком. На created_at из общего TimestampMixin индекс
    # вешаем здесь, а не в миксине, — иначе он достался бы всем таблицам подряд.
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)

    actor_tg_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_admin_username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Длина 45 — под IPv6 в текстовом виде; за nginx сюда попадает адрес человека,
    # а не контейнера (см. interfaces/api/main.py:client_ip).
    actor_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    action: Mapped[AuditAction] = mapped_column(index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    # Тема, к которой относится действие. Без внешнего ключа: журнал обязан пережить
    # удаление темы — иначе история действий исчезала бы вместе с ней.
    theme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
