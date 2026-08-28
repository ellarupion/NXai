import uuid

from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import LlmUsageKind


class LlmUsage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Одно обращение к модели — сколько токенов ушло и во что это обошлось.

    До этой таблицы расход не сохранялся вообще: клиент считал токены и выбрасывал их.
    Ответить «сколько ушло за вчера» было нечем, и когда планировщик без ограничителей
    ушёл в непрерывный рерайт, узнали об этом не из панели, а по счёту от провайдера.

    kind — не имя сервиса, а раздел работы, понятный оператору: он и показывается в
    панели («Рерайт постов», «Разбор по подтемам»). cost_usd считается на месте по
    тарифам из core/llm/pricing.py и СОХРАНЯЕТСЯ, а не пересчитывается на лету: тарифы
    провайдера меняются, и вчерашние расходы должны остаться вчерашними.
    """

    __tablename__ = "llm_usage"
    # Индекс по дате, а не index=True на поле: created_at приходит из общего
    # TimestampMixin, и вешать индекс там значило бы навязать его всем таблицам.
    # Здесь он нужен: по дате фильтруют и сводки, и дневной лимит.
    __table_args__ = (Index("ix_llm_usage_created_at", "created_at"),)

    kind: Mapped[LlmUsageKind] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(String(128))
    # Дорогая часть входа: чтение и запись кэша сюда не входят, у них свои тарифы.
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # На чём именно потратили — кандидат, тема. Без внешнего ключа намеренно: запись о
    # расходе должна пережить удаление того, на что потрачено, иначе месячный итог
    # менялся бы задним числом при чистке.
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Тема, к которой относится расход. Тоже без внешнего ключа и по той же причине;
    # нужна, чтобы показать, какая тема сколько ест: у NXai их несколько, и общий итог
    # не отвечает на вопрос «какую тему пора выключить».
    theme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
