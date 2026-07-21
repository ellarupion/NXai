"""Одобрение/отклонение PENDING_REVIEW-кандидатов, созданных вручную через
"Сделать посты" (core/services/force_generate.py). approve() переводит
кандидата в REWRITTEN — обычный статус для штатного автопаблиш-пайплайна
(core/services/scheduler_pool.py подхватит его на следующем тике так же, как
кандидатов из scheduler.py:dedup_and_rewrite_job, включая шафл/джиттер, см.
ARCHITECTURE.md §5) — approve НЕ публикует напрямую, только снимает "на
паузе" статус ожидания ручной проверки."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.post_version import PostVersion
from core.services.trust_score import REJECTED_PENALTY, adjust_trust_score


class ReviewError(Exception):
    """Текст уходит в HTTP-ответ панели как есть."""


async def _get_pending_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    candidate = await session.get(CandidatePost, candidate_id)
    if candidate is None:
        raise ReviewError("Кандидат не найден")
    if candidate.status is not CandidatePostStatus.PENDING_REVIEW:
        raise ReviewError(
            f"Кандидат в статусе {candidate.status.value}, ожидался pending_review"
        )
    return candidate


async def approve_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    """trust_score уже получил бонус за успешный рерайт в
    core/services/rewrite.py:generate — здесь его не дублируем, approve
    просто снимает статус ожидания ручной проверки."""
    candidate = await _get_pending_candidate(session, candidate_id)
    candidate.status = CandidatePostStatus.REWRITTEN
    await session.flush()
    return candidate


async def edit_candidate_text(
    session: AsyncSession, candidate_id: UUID, new_text: str
) -> PostVersion:
    """Правка текста рерайта перед одобрением (аудит, п.4.1). Не переписываем
    существующую версию на месте, а создаём НОВУЮ PostVersion с
    инкрементированным variant_no и наводим на неё selected_post_version_id —
    так сохраняется исходный LLM-вариант (для сравнения/аудита), а source_
    similarity у ручной правки не считаем (её смысл — анти-плагиат
    LLM-генерации, к ручному тексту неприменим)."""
    new_text = new_text.strip()
    if not new_text:
        raise ReviewError("Текст поста не может быть пустым")

    candidate = await _get_pending_candidate(session, candidate_id)

    existing_versions = await session.scalar(
        select(func.count()).select_from(PostVersion).where(
            PostVersion.candidate_post_id == candidate.id
        )
    )
    version = PostVersion(
        candidate_post_id=candidate.id,
        variant_no=(existing_versions or 0) + 1,
        rewritten_text=new_text,
        persona_prompt_used="",
        source_similarity=None,
    )
    session.add(version)
    await session.flush()
    candidate.selected_post_version_id = version.id
    await session.flush()
    return version


async def reject_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    candidate = await _get_pending_candidate(session, candidate_id)
    candidate.status = CandidatePostStatus.REJECTED
    await session.flush()
    await adjust_trust_score(session, candidate.source_channel_id, -REJECTED_PENALTY)
    return candidate
