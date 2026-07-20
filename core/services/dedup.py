"""DedupService — эмбеддинги, семантический поиск дублей в pgvector (адаптировано
из NX core/services/dedup.py). В NX это было реализовано, но не подключено к
пайплайну; здесь — обязательный шаг между scoring и rewrite (см.
ARCHITECTURE.md §5): один и тот же вирусный пост почти всегда приходит из
нескольких source_channels одной темы одновременно, и сравнивать нужно именно
SELECTED-кандидатов той же темы, а не вообще все когда-либо виденные посты —
иначе дедуп со временем сравнивает с тысячами нерелевантных записей.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings.client import EmbeddingsClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.source_channel import SourceChannel

logger = get_logger(__name__)

HIGH_SIMILARITY_THRESHOLD = 0.92


@dataclass(frozen=True)
class SimilarCandidate:
    candidate_id: UUID
    similarity: float
    score: float | None


class DedupService:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingsClient) -> None:
        self.session = session
        self.embeddings = embeddings

    async def embed_and_store(self, candidate_id: UUID) -> list[float]:
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")

        embedding = await self.embeddings.embed_one(candidate.raw_text)
        candidate.embedding = embedding
        await self.session.flush()

        logger.info("dedup.embedding_stored", candidate_id=str(candidate_id))
        return embedding

    async def find_similar_in_theme(
        self, candidate_id: UUID, theme_id: UUID, embedding: list[float], limit: int = 5
    ) -> list[SimilarCandidate]:
        """pgvector cosine similarity против остальных SELECTED/REWRITTEN/QUEUED/
        PUBLISHED-кандидатов ТОЙ ЖЕ темы — сравнение с ещё не отобранными (NEW/
        SCORING) или уже отклонёнными (REJECTED/DUPLICATE) кандидатами не имеет
        смысла: они и так не попадут в публикацию."""
        distance = CandidatePost.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(CandidatePost.id, distance, CandidatePost.score)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                CandidatePost.id != candidate_id,
                CandidatePost.embedding.is_not(None),
                SourceChannel.theme_id == theme_id,
                CandidatePost.status.in_(
                    [
                        CandidatePostStatus.SELECTED,
                        CandidatePostStatus.REWRITTEN,
                        CandidatePostStatus.QUEUED,
                        CandidatePostStatus.PUBLISHED,
                    ]
                ),
            )
            .order_by(distance)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            SimilarCandidate(candidate_id=row.id, similarity=1 - row.distance, score=row.score)
            for row in result
        ]

    async def resolve_duplicates(self, candidate_id: UUID, theme_id: UUID) -> UUID | None:
        """embed + search + merge одним вызовом. Если найден кандидат с cosine
        similarity >= HIGH_SIMILARITY_THRESHOLD, сравнивает score и помечает
        DUPLICATE того, у кого он ниже (representative остаётся SELECTED и идёт в
        rewrite). Возвращает id representative, если текущий кандидат был свёрнут
        как дубликат, иначе None (текущий кандидат уникален или сам стал
        representative)."""
        embedding = await self.embed_and_store(candidate_id)
        similar = await self.find_similar_in_theme(candidate_id, theme_id, embedding)
        duplicates = [c for c in similar if c.similarity >= HIGH_SIMILARITY_THRESHOLD]
        if not duplicates:
            return None

        candidate = await self.session.get(CandidatePost, candidate_id)
        best_duplicate = max(duplicates, key=lambda c: c.score or 0.0)

        if (candidate.score or 0.0) >= (best_duplicate.score or 0.0):
            # Текущий кандидат сильнее — сворачиваем найденный дубль в него.
            other = await self.session.get(CandidatePost, best_duplicate.candidate_id)
            other.status = CandidatePostStatus.DUPLICATE
            other.duplicate_of_id = candidate.id
            await self.session.flush()
            logger.info(
                "dedup.merged_other_into_current",
                candidate_id=str(candidate_id),
                merged_id=str(best_duplicate.candidate_id),
            )
            return None

        candidate.status = CandidatePostStatus.DUPLICATE
        candidate.duplicate_of_id = best_duplicate.candidate_id
        await self.session.flush()
        logger.info(
            "dedup.current_merged_into_other",
            candidate_id=str(candidate_id),
            representative_id=str(best_duplicate.candidate_id),
        )
        return best_duplicate.candidate_id
