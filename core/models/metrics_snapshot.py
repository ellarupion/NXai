import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, UUIDPrimaryKeyMixin


class CandidateMetricsSnapshot(Base, UUIDPrimaryKeyMixin):
    """Точка временного ряда views/forwards ЧУЖОГО поста (candidate_post) —
    собирается Telethon-скорером на контрольных отметках +30м/+2ч/+6ч после
    first_seen_at (см. ARCHITECTURE.md §5: пост должен "дозреть", разовый
    просмотр числа пересылок ненадёжен). Несколько строк на один
    candidate_post, а не одно JSONB-поле, как Publication.metrics в NX —
    здесь важна именно динамика (скорость набора форвардов), а не только
    последнее значение."""

    __tablename__ = "candidate_metrics_snapshots"

    candidate_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_posts.id", ondelete="CASCADE"), index=True
    )
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forwards: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublicationMetricsSnapshot(Base, UUIDPrimaryKeyMixin):
    """То же самое, но для СВОЕЙ публикации (Publication) — переиспользует ту
    же идею временного ряда вместо разового JSONB, как было в NX
    Publication.metrics, чтобы дашборды (core/services/analytics.py) могли
    строить графики роста, а не только карточку "на сейчас"."""

    __tablename__ = "publication_metrics_snapshots"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), index=True
    )
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forwards: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reactions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
