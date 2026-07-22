import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from core.models.enums import CandidatePostStatus

if TYPE_CHECKING:
    from core.models.post_version import PostVersion
    from core.models.source_channel import SourceChannel

# Размерность эмбеддингов Voyage AI (voyage-3), совпадает с
# core/embeddings/client.py:EMBEDDING_MODEL. Смена модели требует смены
# размерности колонки/новой миграции — как и в NX core/models/draft.py.
EMBEDDING_DIM = 1024


class CandidatePost(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Пост, увиденный ingest-воркером в чужом source_channel. Аналог NX Draft,
    но НЕ создаётся сразу готовым к публикации: проходит
    NEW → SCORING → SELECTED → REWRITTEN → QUEUED → PUBLISHED, либо
    REJECTED/DUPLICATE по дороге (core/models/enums.py:CandidatePostStatus,
    полное описание переходов — core/services/scoring.py и
    core/services/dedup.py)."""

    __tablename__ = "candidate_posts"
    __table_args__ = (
        UniqueConstraint(
            "source_channel_id", "tg_message_id", name="uq_candidate_source_channel_message"
        ),
    )

    source_channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_channels.id", ondelete="CASCADE")
    )
    tg_message_id: Mapped[int] = mapped_column(BigInteger)
    raw_text: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Медиа НЕ храним байтами: держим ссылку (source_channel + tg_message_id уже
    # есть) и докачиваем фото через Telethon-сессию источника в момент публикации
    # (core/services/media.py), затем отправляем ботом. has_media=True ставится на
    # ingest'е, если у поста было фото — без этого пост-картинка с подписью
    # проходил бы мимо пайплайна (аудит, п.5.1). media_group_id — id альбома
    # Telegram (grouped_id): у альбома несколько tg-сообщений с общим id, при
    # публикации собираем все фото группы.
    has_media: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    media_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[CandidatePostStatus] = mapped_column(default=CandidatePostStatus.NEW, index=True)
    # Нормализованный скор из core/services/scoring.py (forwards / медиана канала за
    # 7 дней) — заполняется на каждом контрольном снапшоте, финальное значение перед
    # выбором в SELECTED берётся из последнего доступного core/models/metrics_snapshot.py.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # «Отклонить с причиной» (UX-этап 5): слаг причины из фиксированного
    # набора (too_long/officialese/wrong_tone/watery/lost_point/ad) — сигналы
    # копятся в сводку у бота темы (rejection-stats) как подсказки, что
    # поправить в персоне. NULL — отклонён без причины или не отклонялся.
    rejection_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # Self-FK: если дедуп находит более ранний кандидат с cosine similarity выше
    # HIGH_SIMILARITY_THRESHOLD, текущий помечается DUPLICATE и указывает на
    # representative (обычно — на кандидата с более высоким score).
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_posts.id", ondelete="SET NULL"), nullable=True
    )
    # use_alter=True: candidate_posts <-> post_versions ссылаются друг на друга
    # (post_versions.candidate_post_id -> candidate_posts.id), поэтому в одной
    # общей миграции ни одну из двух таблиц нельзя создать первой со всеми её
    # FK инлайн — Postgres откажет "relation does not exist" на второй таблице.
    # use_alter просит SQLAlchemy/Alembic вынести именно этот FK в отдельный
    # ALTER TABLE ... ADD CONSTRAINT после того, как обе таблицы уже созданы.
    selected_post_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "post_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_candidate_posts_selected_post_version_id",
        ),
        nullable=True,
    )

    source_channel: Mapped["SourceChannel"] = relationship(back_populates="candidate_posts")
    versions: Mapped[list["PostVersion"]] = relationship(
        back_populates="candidate_post", foreign_keys="PostVersion.candidate_post_id"
    )
