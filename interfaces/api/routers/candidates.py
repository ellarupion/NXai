"""«Сделать посты» — принудительный внеочередной прогон пайплайна на тему
(core/services/force_generate.py) — и одобрение/отклонение того, что он
сгенерировал (core/services/review.py), прежде чем это станет обычным
REWRITTEN-кандидатом, доступным штатному автопаблишу."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import AuditAction, CandidatePostStatus
from core.models.post_version import PostVersion
from core.models.source_channel import SourceChannel
from core.services.audit import record_audit
from core.services.effective_settings import get_effective_settings
from core.services.force_generate import ForceGenerateError, ForceGenerateService
from core.services.media import download_candidate_photos_by_id
from core.services.review import (
    AlreadyHandledError,
    ReviewError,
    approve_candidate,
    edit_candidate_text,
    reject_all_pending,
    reject_candidate,
    restore_rejected,
    unapprove_candidate,
)
from interfaces.api.auth import CurrentAdmin, get_current_admin
from interfaces.api.deps import get_db
from interfaces.bots.notify import push_review_cards
from core.models.theme import Theme
from core.models.post_passport import PostPassport
from core.services.daily_batch import daily_target, order_batch, today_in_project_tz
from core.services.llm_usage import spent_on_entity
from core.services.llm_budget import DailyBudgetExceededError, ensure_budget

router = APIRouter(prefix="/candidates", tags=["candidates"], dependencies=[Depends(get_current_admin)])

MAX_GENERATE_COUNT = 10


async def _theme_of(session: AsyncSession, candidate_id: UUID) -> UUID | None:
    """Тема поста для записи в журнал — чтобы журнал можно было отфильтровать по теме.

    Отдельным запросом, а не по загруженному кандидату: к моменту записи он уже
    может быть отклонён и выгружен из сессии, а тема нужна независимо от исхода."""
    return await session.scalar(
        select(SourceChannel.theme_id)
        .join(CandidatePost, CandidatePost.source_channel_id == SourceChannel.id)
        .where(CandidatePost.id == candidate_id)
    )


class GenerateRequest(BaseModel):
    theme_id: UUID
    count: int = 3


class DailyBatchRequest(BaseModel):
    theme_id: UUID


class DailyBatchOut(BaseModel):
    ordered: int
    delivered: int
    posts: list["GeneratedPostOut"]


class GeneratedPostOut(BaseModel):
    candidate_id: UUID
    source_channel_title: str
    rewritten_text: str
    score: float | None


class PendingReviewOut(BaseModel):
    candidate_id: UUID
    # Nullable: source_channels.theme_id — ON DELETE SET NULL, поэтому после
    # удаления темы её PENDING_REVIEW-кандидаты остаются, но уже без темы.
    # С обязательным UUID здесь Pydantic ронял ВЕСЬ список проверки в 500.
    theme_id: UUID | None
    source_channel_title: str
    raw_text: str
    rewritten_text: str
    score: float | None
    created_at: datetime
    has_media: bool
    # None — у темы не заданы рубрики либо классификатор не отработал.
    rubric: str | None = None


@router.post("/generate", response_model=list[GeneratedPostOut])
async def generate_posts(
    payload: GenerateRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> list[GeneratedPostOut]:
    try:
        await ensure_budget(session)
    except DailyBudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    count = max(1, min(payload.count, MAX_GENERATE_COUNT))
    settings = await get_effective_settings(session)
    try:
        results = await ForceGenerateService(session, settings).generate(payload.theme_id, count)
    except ForceGenerateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit(
        session,
        AuditAction.GENERATE,
        "theme",
        str(payload.theme_id),
        {"requested": count, "delivered": len(results), "mode": "count"},
        actor_admin_username=current.username,
        theme_id=payload.theme_id,
    )
    await session.commit()

    # Дублируем свежую очередь в admin-бот карточками с кнопками (аудит, п.6.1):
    # можно одобрять прямо из Telegram, не открывая панель.
    await push_review_cards(
        session,
        [
            {
                "candidate_id": r.candidate_id,
                "source_channel_title": r.source_channel_title,
                "rewritten_text": r.rewritten_text,
                "score": r.score,
            }
            for r in results
        ],
    )

    return [
        GeneratedPostOut(
            candidate_id=r.candidate_id,
            source_channel_title=r.source_channel_title,
            rewritten_text=r.rewritten_text,
            score=r.score,
        )
        for r in results
    ]


@router.post("/daily-batch", response_model=DailyBatchOut)
async def generate_daily_batch(
    payload: DailyBatchRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> DailyBatchOut:
    """«Посты на сегодня»: одна партия размером в дневное расписание темы.

    Размер не спрашиваем — он уже задан кадансом бота. Заказ запоминается на
    теме, и дальше планировщик добирает партию сам, если оператор что-то
    отклонит: долг считается как «заказано минус одобренное и ждущее»
    (core/services/daily_batch.py). Повторная просьба в тот же день заказ не
    удваивает."""
    theme = await session.get(Theme, payload.theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Тема не найдена")

    try:
        await ensure_budget(session)
    except DailyBudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    size = await daily_target(session, payload.theme_id)
    today = await today_in_project_tz(session)
    settings = await get_effective_settings(session)
    try:
        results = await ForceGenerateService(session, settings).generate(
            payload.theme_id, size, batch_date=today
        )
    except ForceGenerateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Заказ отмечаем ПОСЛЕ успешной генерации: упади она на ключах LLM —
    # тема осталась бы с долгом, который планировщик принялся бы гасить сам,
    # молча и в фоне. А оператор просил партию именно сейчас и видел ошибку.
    await order_batch(session, theme, size)
    await record_audit(
        session,
        AuditAction.GENERATE,
        "theme",
        str(payload.theme_id),
        {"requested": size, "delivered": len(results), "mode": "batch", "batch_date": str(today)},
        actor_admin_username=current.username,
        theme_id=payload.theme_id,
    )
    await session.commit()

    await push_review_cards(
        session,
        [
            {
                "candidate_id": r.candidate_id,
                "source_channel_title": r.source_channel_title,
                "rewritten_text": r.rewritten_text,
                "score": r.score,
            }
            for r in results
        ],
    )
    return DailyBatchOut(
        ordered=size,
        delivered=len(results),
        posts=[
            GeneratedPostOut(
                candidate_id=r.candidate_id,
                source_channel_title=r.source_channel_title,
                rewritten_text=r.rewritten_text,
                score=r.score,
            )
            for r in results
        ],
    )


class PassportOut(BaseModel):
    """Все поля необязательные: паспорт лежит в JSON, и записи, сделанные до появления
    очередного поля, его просто не знают. Требовать их означало бы ронять карточку на
    постах, которые прошли конвейер раньше."""

    candidate_id: UUID
    source_channel_title: str | None = None
    facts: dict
    # Сколько стоил этот пост. Считаем запросом к расходам, а не храним в паспорте:
    # второе место для того же числа рано или поздно разъедется с первым.
    cost_usd: float
    cost_by_kind: list[dict]


@router.get("/{candidate_id}/passport", response_model=PassportOut)
async def candidate_passport(
    candidate_id: UUID, session: AsyncSession = Depends(get_db)
) -> PassportOut:
    """«Почему вышел именно такой пост». Отдельным запросом, а не в составе карточки:
    паспорт открывают по одному и по требованию, а очередь читается сотнями строк."""
    candidate = await session.get(CandidatePost, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Пост не найден")

    passport = (
        await session.execute(
            select(PostPassport).where(PostPassport.candidate_post_id == candidate_id)
        )
    ).scalar_one_or_none()

    source = await session.get(SourceChannel, candidate.source_channel_id)
    cost, by_kind = await spent_on_entity(session, candidate_id)

    return PassportOut(
        candidate_id=candidate_id,
        source_channel_title=source.title if source else None,
        facts=(passport.data if passport else {}),
        cost_usd=round(cost, 6),
        cost_by_kind=[{"title": k.title, "cost_usd": round(k.cost_usd, 6), "calls": k.calls} for k in by_kind],
    )


@router.get("/pending-review", response_model=list[PendingReviewOut])
async def list_pending_review(
    theme_id: UUID | None = None, session: AsyncSession = Depends(get_db)
) -> list[PendingReviewOut]:
    stmt = (
        select(CandidatePost, SourceChannel, PostVersion)
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .join(PostVersion, PostVersion.id == CandidatePost.selected_post_version_id)
        .where(CandidatePost.status == CandidatePostStatus.PENDING_REVIEW)
        .order_by(CandidatePost.created_at.desc())
    )
    if theme_id is not None:
        stmt = stmt.where(SourceChannel.theme_id == theme_id)

    result = await session.execute(stmt)
    return [
        PendingReviewOut(
            candidate_id=candidate.id,
            theme_id=source_channel.theme_id,
            source_channel_title=source_channel.title,
            raw_text=candidate.raw_text,
            rewritten_text=post_version.rewritten_text,
            score=candidate.score,
            created_at=candidate.created_at,
            has_media=candidate.has_media,
            rubric=candidate.rubric,
        )
        for candidate, source_channel, post_version in result.all()
    ]


class ThemePendingCount(BaseModel):
    theme_id: UUID | None
    count: int


@router.get("/pending-review/counts", response_model=list[ThemePendingCount])
async def pending_review_counts(session: AsyncSession = Depends(get_db)) -> list[ThemePendingCount]:
    """Сколько постов ждёт одобрения в каждой теме — для вкладок в «Проверке».
    Отдельным GROUP BY, а не подсчётом на фронте: иначе ради счётчиков пришлось
    бы тянуть весь неотфильтрованный список."""
    rows = await session.execute(
        select(SourceChannel.theme_id, func.count())
        .join(CandidatePost, CandidatePost.source_channel_id == SourceChannel.id)
        .where(CandidatePost.status == CandidatePostStatus.PENDING_REVIEW)
        .group_by(SourceChannel.theme_id)
    )
    return [ThemePendingCount(theme_id=theme_id, count=count) for theme_id, count in rows.all()]


class RejectAllPayload(BaseModel):
    # None — отклонить во ВСЕХ темах. Панель в этом случае обязана спросить
    # подтверждение с числом: разница между «почистил одну тему» и «снёс всё»
    # огромная, а кнопка одна и та же.
    theme_id: UUID | None = None


class RejectAllResult(BaseModel):
    count: int
    # Отклонённые id — панель держит их для окна отмены.
    candidate_ids: list[UUID]


@router.post("/reject-all", response_model=RejectAllResult)
async def reject_all(
    payload: RejectAllPayload,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> RejectAllResult:
    ids = await reject_all_pending(session, payload.theme_id)
    # Одна запись на всю очистку, а не по записи на пост: в журнале важно само
    # решение «стереть очередь», а список постов уже лежит в payload.
    await record_audit(
        session,
        AuditAction.REJECT_ALL,
        "theme",
        str(payload.theme_id) if payload.theme_id else "",
        {"count": len(ids)},
        actor_admin_username=current.username,
        theme_id=payload.theme_id,
    )
    await session.commit()
    return RejectAllResult(count=len(ids), candidate_ids=ids)


class RestorePayload(BaseModel):
    candidate_ids: list[UUID]


class RestoreResult(BaseModel):
    restored: int


@router.post("/restore", response_model=RestoreResult)
async def restore(
    payload: RestorePayload,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> RestoreResult:
    """Откат массового отклонения — «Отклонить все» стирает очередь одним
    нажатием, и без отмены это была бы самая дорогая ошибка в панели."""
    restored = await restore_rejected(session, payload.candidate_ids)
    await record_audit(
        session,
        AuditAction.RESTORE,
        "candidate",
        str(payload.candidate_ids[0]) if payload.candidate_ids else "",
        {"restored": restored, "requested": len(payload.candidate_ids)},
        actor_admin_username=current.username,
    )
    await session.commit()
    return RestoreResult(restored=restored)


class EditTextRequest(BaseModel):
    text: str


@router.put("/{candidate_id}/text", status_code=204)
async def edit_text(
    candidate_id: UUID,
    payload: EditTextRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> None:
    try:
        await edit_candidate_text(session, candidate_id, payload.text)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Текст правки в журнал не кладём — он и так лежит новой версией поста, а
    # журнал должен оставаться читаемым списком, а не свалкой абзацев.
    await record_audit(
        session,
        AuditAction.EDIT,
        "candidate",
        str(candidate_id),
        {"length": len(payload.text)},
        actor_admin_username=current.username,
        theme_id=await _theme_of(session, candidate_id),
    )
    await session.commit()


@router.get("/{candidate_id}/media")
async def get_candidate_media(
    candidate_id: UUID, session: AsyncSession = Depends(get_db)
) -> Response:
    """Превью медиа кандидата в Review (аудит, п.5.3): качает первое фото из
    источника через его Telethon-сессию и отдаёт как image/jpeg. Байты нигде
    не кэшируются — тянутся по запросу страницы; для очереди на одобрение
    (единицы постов) это приемлемо."""
    settings = await get_effective_settings(session)
    photos = await download_candidate_photos_by_id(session, candidate_id, settings)
    if not photos:
        raise HTTPException(status_code=404, detail="У поста нет доступного медиа")
    return Response(content=photos[0], media_type="image/jpeg")


@router.post("/{candidate_id}/approve", status_code=204)
async def approve(
    candidate_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> None:
    try:
        await approve_candidate(session, candidate_id)
    except AlreadyHandledError as exc:
        # 409, а не 400: панель по коду понимает, что это рассинхрон списка, и
        # молча обновляет его вместо красной ошибки оператору.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        session,
        AuditAction.APPROVE,
        "candidate",
        str(candidate_id),
        {"via": "panel"},
        actor_admin_username=current.username,
        theme_id=await _theme_of(session, candidate_id),
    )
    await session.commit()


@router.post("/{candidate_id}/unapprove", status_code=204)
async def unapprove(
    candidate_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> None:
    """Откат одобрения в короткое окно отмены (UX-аудит, №2) — пост
    возвращается в «Проверку». Если планировщик уже забрал его в публикацию,
    сервис вернёт 400 с объяснением."""
    try:
        await unapprove_candidate(session, candidate_id)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        session,
        AuditAction.UNAPPROVE,
        "candidate",
        str(candidate_id),
        actor_admin_username=current.username,
        theme_id=await _theme_of(session, candidate_id),
    )
    await session.commit()


class RejectPayload(BaseModel):
    # Слаг причины из core/services/review.py:REJECTION_REASONS; None —
    # отклонить без причины (например, хоткеем D).
    reason: str | None = None


@router.post("/{candidate_id}/reject", status_code=204)
async def reject(
    candidate_id: UUID,
    payload: RejectPayload | None = None,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> None:
    try:
        await reject_candidate(session, candidate_id, payload.reason if payload else None)
    except AlreadyHandledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        session,
        AuditAction.REJECT,
        "candidate",
        str(candidate_id),
        {"via": "panel", "reason": payload.reason if payload else None},
        actor_admin_username=current.username,
        theme_id=await _theme_of(session, candidate_id),
    )
    await session.commit()
