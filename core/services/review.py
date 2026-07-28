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
from core.models.source_channel import SourceChannel
from core.models.enums import CandidatePostStatus
from core.models.post_version import PostVersion
from core.services.trust_score import REJECTED_PENALTY, adjust_trust_score


class ReviewError(Exception):
    """Текст уходит в HTTP-ответ панели как есть."""


class AlreadyHandledError(ReviewError):
    """Пост уже одобрен/отклонён кем-то ещё или в соседней вкладке. Не ошибка
    оператора: панели достаточно молча обновить список."""


async def _get_pending_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    candidate = await session.get(CandidatePost, candidate_id)
    if candidate is None:
        raise ReviewError("Кандидат не найден")
    if candidate.status is not CandidatePostStatus.PENDING_REVIEW:
        # Техническое «в статусе rejected, ожидался pending_review» вылезало
        # оператору в панель при любом расхождении списка с базой (второй
        # клик, открытая в двух вкладках «Проверка», массовое отклонение
        # рядом). Причина всегда одна и та же и от оператора не зависит.
        raise AlreadyHandledError("Этот пост уже обработан — список обновлён")
    return candidate


async def approve_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    """trust_score уже получил бонус за успешный рерайт в
    core/services/rewrite.py:generate — здесь его не дублируем, approve
    просто снимает статус ожидания ручной проверки."""
    candidate = await _get_pending_candidate(session, candidate_id)
    candidate.status = CandidatePostStatus.REWRITTEN
    await session.flush()
    return candidate


async def unapprove_candidate(session: AsyncSession, candidate_id: UUID) -> CandidatePost:
    """Отмена одобрения (UX-аудит, №2). Одобрение — единственное необратимое
    действие в «Проверке», причём самое дешёвое: одна клавиша A, без
    подтверждения. Подтверждение убило бы скорость разбора очереди, поэтому
    вместо него — короткое окно отмены.

    Работает, только пока планировщик не забрал пост: из REWRITTEN он уходит в
    QUEUED/PUBLISHED на ближайшем тике, и «отменить» после этого нечего —
    сообщаем честно, а не делаем вид, что откатили."""
    candidate = await session.get(CandidatePost, candidate_id)
    if candidate is None:
        raise ReviewError("Кандидат не найден")
    if candidate.status is CandidatePostStatus.PENDING_REVIEW:
        return candidate  # уже вернули (двойной клик по «Отменить») — не ошибка
    if candidate.status is not CandidatePostStatus.REWRITTEN:
        raise ReviewError(
            "Пост уже ушёл дальше по конвейеру — отменить одобрение нельзя"
        )
    candidate.status = CandidatePostStatus.PENDING_REVIEW
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


# Фиксированные причины отклонения («Отклонить с причиной», UX-этап 5).
# Слаг -> русская подпись; сводка по ним живёт у бота темы (rejection-stats).
REJECTION_REASONS: dict[str, str] = {
    "too_long": "слишком длинно",
    "officialese": "канцелярит",
    "wrong_tone": "не тот тон",
    "watery": "вода",
    "lost_point": "потерял суть",
    "ad": "реклама/мусор",
}


async def reject_candidate(
    session: AsyncSession, candidate_id: UUID, reason: str | None = None
) -> CandidatePost:
    if reason is not None and reason not in REJECTION_REASONS:
        raise ReviewError(f"Неизвестная причина отклонения: {reason}")
    candidate = await _get_pending_candidate(session, candidate_id)
    candidate.status = CandidatePostStatus.REJECTED
    candidate.rejection_reason = reason
    await session.flush()
    await adjust_trust_score(session, candidate.source_channel_id, -REJECTED_PENALTY)
    return candidate


async def reject_all_pending(
    session: AsyncSession, theme_id: UUID | None = None
) -> list[UUID]:
    """Массовая чистка очереди проверки.

    Намеренно НЕ ставит причину и НЕ трогает trust_score источников, в отличие
    от поштучного reject_candidate: «отклонить все» — это про объём («накопилось
    за неделю, разбирать нечего»), а не про качество конкретных источников.
    Иначе одна кнопка молча обрушила бы рейтинги всем каналам разом. Обучающий
    сигнал даёт только поштучное отклонение с причиной.

    Возвращает id отклонённых — из них панель собирает окно отмены."""
    stmt = select(CandidatePost).where(CandidatePost.status == CandidatePostStatus.PENDING_REVIEW)
    if theme_id is not None:
        stmt = stmt.join(
            SourceChannel, SourceChannel.id == CandidatePost.source_channel_id
        ).where(SourceChannel.theme_id == theme_id)

    candidates = list((await session.execute(stmt)).scalars().all())
    for candidate in candidates:
        candidate.status = CandidatePostStatus.REJECTED
    await session.flush()
    return [c.id for c in candidates]


async def restore_rejected(session: AsyncSession, candidate_ids: list[UUID]) -> int:
    """Откат массового отклонения. Возвращает в проверку только те посты, что
    всё ещё REJECTED, — остальные кто-то успел тронуть, и переписывать их
    статус поверх чужого решения нельзя."""
    if not candidate_ids:
        return 0
    result = await session.execute(
        select(CandidatePost).where(
            CandidatePost.id.in_(candidate_ids),
            CandidatePost.status == CandidatePostStatus.REJECTED,
        )
    )
    restored = list(result.scalars().all())
    for candidate in restored:
        candidate.status = CandidatePostStatus.PENDING_REVIEW
        candidate.rejection_reason = None
    await session.flush()
    return len(restored)
