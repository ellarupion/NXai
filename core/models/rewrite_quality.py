import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import QualityRunStatus, QualityVerdict


class RewriteQualityRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Один замер: «что работает сейчас» против «что проверяем».

    До этого про качество текстов не было ни одного числа. Поменяли персону или
    модель — стало лучше или хуже, судили по ощущению от последних просмотренных
    постов, а это ровно тот способ, которым люди подтверждают то, во что уже верят.

    Замер отвечает числом: на одинаковом наборе исходников готовятся два варианта
    каждого поста, судья сравнивает их вслепую, и получается «новый вариант выигрывает
    в 62 случаях из 100».
    """

    __tablename__ = "rewrite_quality_runs"

    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        # Без FK-каскада, но с SET NULL: замер переживает удаление темы. Вывод «эта
        # персона писала лучше» ценен и после того, как тему закрыли.
        UUID(as_uuid=True), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")

    # Что именно сравниваем. Персоны храним ТЕКСТОМ, а не ссылкой на бота: персона
    # правится каждый день, и через неделю ссылка указывала бы на другой текст —
    # замер стал бы невоспроизводимым, а его число бессмысленным.
    baseline_persona: Mapped[str] = mapped_column(Text, default="")
    variant_persona: Mapped[str] = mapped_column(Text, default="")
    baseline_model: Mapped[str] = mapped_column(String(120), default="")
    variant_model: Mapped[str] = mapped_column(String(120), default="")

    size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[QualityRunStatus] = mapped_column(
        default=QualityRunStatus.PENDING, index=True
    )
    # Итог считаем и храним: пересчитывать его на каждом открытии страницы значит
    # каждый раз заново решать, как считаются ничьи, — а решение должно быть одно.
    wins_baseline: Mapped[int] = mapped_column(Integer, default=0)
    wins_variant: Mapped[int] = mapped_column(Integer, default=0)
    ties: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pairs: Mapped[list["RewriteQualityPair"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RewriteQualityPair(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Один исходник и два переписанных варианта с приговором судьи.

    Исходник хранится текстом-снимком, а не ссылкой на кандидата: кандидатов чистят,
    а замер должен оставаться проверяемым — человек открывает пару и сам смотрит, за
    что судья присудил победу.
    """

    __tablename__ = "rewrite_quality_pairs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rewrite_quality_runs.id", ondelete="CASCADE"), index=True
    )
    source_text: Mapped[str] = mapped_column(Text)
    baseline_text: Mapped[str] = mapped_column(Text, default="")
    variant_text: Mapped[str] = mapped_column(Text, default="")

    # Два приговора на пару: тот же выбор судят дважды, меняя варианты местами.
    # Модели свойственно предпочитать текст, который показали первым, и без второго
    # прохода замер измерял бы это предпочтение вместо качества.
    verdict_direct: Mapped[QualityVerdict | None] = mapped_column(nullable=True)
    verdict_swapped: Mapped[QualityVerdict | None] = mapped_column(nullable=True)
    # Итог пары: совпали приговоры — победа, разошлись — ничья.
    verdict: Mapped[QualityVerdict | None] = mapped_column(nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")

    run: Mapped["RewriteQualityRun"] = relationship(back_populates="pairs")
