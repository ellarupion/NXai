"""«Сделать посты» — принудительный внеочередной прогон пайплайна на тему
(core/services/force_generate.py) — и одобрение/отклонение того, что он
сгенерировал (core/services/review.py), прежде чем это станет обычным
REWRITTEN-кандидатом, доступным штатному автопаблишу."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus
from core.models.post_version import PostVersion
from core.models.source_channel import SourceChannel
from core.services.effective_settings import get_effective_settings
from core.services.force_generate import ForceGenerateError, ForceGenerateService
from core.services.media import download_candidate_photos_by_id
from core.services.review import (
    ReviewError,
    approve_candidate,
    edit_candidate_text,
    reject_candidate,
)
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/candidates", tags=["candidates"], dependencies=[Depends(get_current_admin)])

MAX_GENERATE_COUNT = 10


class GenerateRequest(BaseModel):
    theme_id: UUID
    count: int = 3


class GeneratedPostOut(BaseModel):
    candidate_id: UUID
    source_channel_title: str
    rewritten_text: str
    score: float | None


class PendingReviewOut(BaseModel):
    candidate_id: UUID
    theme_id: UUID
    source_channel_title: str
    raw_text: str
    rewritten_text: str
    score: float | None
    created_at: datetime
    has_media: bool


@router.post("/generate", response_model=list[GeneratedPostOut])
async def generate_posts(payload: GenerateRequest, session: AsyncSession = Depends(get_db)) -> list[GeneratedPostOut]:
    count = max(1, min(payload.count, MAX_GENERATE_COUNT))
    settings = await get_effective_settings(session)
    try:
        results = await ForceGenerateService(session, settings).generate(payload.theme_id, count)
    except ForceGenerateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        GeneratedPostOut(
            candidate_id=r.candidate_id,
            source_channel_title=r.source_channel_title,
            rewritten_text=r.rewritten_text,
            score=r.score,
        )
        for r in results
    ]


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
        )
        for candidate, source_channel, post_version in result.all()
    ]


class EditTextRequest(BaseModel):
    text: str


@router.put("/{candidate_id}/text", status_code=204)
async def edit_text(
    candidate_id: UUID, payload: EditTextRequest, session: AsyncSession = Depends(get_db)
) -> None:
    try:
        await edit_candidate_text(session, candidate_id, payload.text)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
async def approve(candidate_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    try:
        await approve_candidate(session, candidate_id)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()


@router.post("/{candidate_id}/reject", status_code=204)
async def reject(candidate_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    try:
        await reject_candidate(session, candidate_id)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
