"""Одобрение/отклонение PENDING_REVIEW-кандидатов, созданных вручную через
"Сделать посты" (core/services/force_generate.py). approve() переводит
кандидата в REWRITTEN — обычный статус для штатного автопаблиш-пайплайна
(core/services/scheduler_pool.py подхватит его на следующем тике так же, как
кандидатов из scheduler.py:dedup_and_rewrite_job, включая шафл/джиттер, см.
ARCHITECTURE.md §5) — approve НЕ публикует напрямую, только снимает "на
паузе" статус ожидания ручной проверки."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
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


async def reject_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    candidate = await _get_pending_candidate(session, candidate_id)
    candidate.status = CandidatePostStatus.REJECTED
    await session.flush()
    await adjust_trust_score(session, candidate.source_channel_id, -REJECTED_PENALTY)
    return candidate
