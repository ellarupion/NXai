"""RewriteService — LLM-рерайт SELECTED-кандидата под персону темы (см.
ARCHITECTURE.md §5). В отличие от DraftGenerationService в NX (сокращение/
расширение уже готового авторского текста по кнопке редактора), здесь рерайт
обязателен для каждого кандидата и явно нацелен на то, чтобы НЕ повторять
структуру исходного поста — иначе результат легко опознать как копию
источника (см. ROADMAP.md Phase 1)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings.client import EmbeddingsClient
from core.llm.client import REWRITE_MODEL, LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.post_version import PostVersion

logger = get_logger(__name__)

ANTI_COPY_INSTRUCTIONS = """\
Перепиши пост своими словами для тематического Telegram-канала. Требования:
- не сохраняй порядок абзацев и зачин исходного текста — переставь факты;
- не копируй формулировки дословно, кроме имён/цифр/названий;
- подстрой длину и тон под персону канала (см. системный промпт);
- не добавляй ссылки/упоминания исходного канала.
"""


class RewriteService:
    def __init__(self, session: AsyncSession, llm: LLMClient, embeddings: EmbeddingsClient) -> None:
        self.session = session
        self.llm = llm
        self.embeddings = embeddings

    async def generate(self, candidate_id: UUID, persona_prompt: str) -> PostVersion:
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if candidate.status is not CandidatePostStatus.SELECTED:
            raise ValueError(f"CandidatePost {candidate.id} is {candidate.status.value}, expected selected")

        system_prompt = f"{persona_prompt}\n\n{ANTI_COPY_INSTRUCTIONS}"
        result = await self.llm.complete(
            model=REWRITE_MODEL,
            system_prompt=system_prompt,
            user_prompt=candidate.raw_text,
        )

        source_similarity = await self._similarity(candidate.raw_text, result.text)

        # Не candidate.versions (ленивая relationship — синхронный доступ к ней
        # под asyncpg падает MissingGreenlet, раз объект не был явно предзагружен
        # selectinload/joinedload): считаем напрямую запросом.
        existing_versions = await self.session.scalar(
            select(func.count()).select_from(PostVersion).where(PostVersion.candidate_post_id == candidate.id)
        )
        variant_no = (existing_versions or 0) + 1
        version = PostVersion(
            candidate_post_id=candidate.id,
            variant_no=variant_no,
            rewritten_text=result.text,
            persona_prompt_used=persona_prompt,
            source_similarity=source_similarity,
        )
        self.session.add(version)
        await self.session.flush()

        candidate.selected_post_version_id = version.id
        candidate.status = CandidatePostStatus.REWRITTEN
        await self.session.flush()

        logger.info(
            "rewrite.generated",
            candidate_id=str(candidate_id),
            post_version_id=str(version.id),
            source_similarity=source_similarity,
        )
        return version

    async def _similarity(self, raw_text: str, rewritten_text: str) -> float:
        """embedding-дистанция рерайта от оригинала — метрика анти-плагиата
        (см. core/models/post_version.py:PostVersion.source_similarity),
        считается той же моделью, что и дедуп, без отдельного вызова pgvector:
        для пары текстов проще посчитать косинус в Python, чем гонять через БД."""
        raw_embedding, rewritten_embedding = await self.embeddings.embed([raw_text, rewritten_text])
        return _cosine_similarity(raw_embedding, rewritten_embedding)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
