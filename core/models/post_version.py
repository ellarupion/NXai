import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from core.models.candidate_post import CandidatePost


class PostVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Рерайт-версия кандидата, созданная core/services/rewrite.py. variant_no
    растёт, если рерайт перегенерировался (например, редактор в панели попросил
    "ещё раз"). persona_prompt_used — снимок промпта темы на момент генерации
    (для аудита, если персону потом поменяют). source_similarity — метрика
    анти-плагиата: embedding-дистанция rewritten_text от raw_text исходного
    кандидата (близко к 1.0 = рерайт почти не отличается от источника, тревога;
    считается тем же core/embeddings/client.py, что и дедуп)."""

    __tablename__ = "post_versions"

    candidate_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_posts.id", ondelete="CASCADE")
    )
    variant_no: Mapped[int] = mapped_column(Integer, default=1)
    rewritten_text: Mapped[str] = mapped_column(Text)
    persona_prompt_used: Mapped[str] = mapped_column(Text, default="")
    source_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    candidate_post: Mapped["CandidatePost"] = relationship(
        back_populates="versions", foreign_keys=[candidate_post_id]
    )
