"""Лента вышедшего — то, чего в панели не было вовсе (UX-аудит, №3).

Конвейер был спроектирован «слева направо»: источник → скоринг → рерайт →
одобрение → выход. За точкой выхода начинался обрыв: единственным следом
публикации были пять строк превью в свёрнутом блоке на «Очереди». Из-за этого
не работал целый класс сценариев — «откуда пришёл плохой пост», «этот источник
поставляет мусор», «что зашло за месяц».

Здесь публикация собирается обратно в цепочку: текст, который вышел → канал и
тема → кандидат-предок и его исходный пост → источник, откуда его взяли →
персона, которой его переписали → метрики отдачи. Всё это уже лежало в БД,
не хватало только соединяющего запроса — новых таблиц и миграций не нужно.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.enums import PublicationSource
from core.models.metrics_snapshot import PublicationMetricsSnapshot
from core.models.pool_post import PoolPost
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.theme import Theme
from core.services.persona_learning import remember_good_example
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/publications", tags=["publications"], dependencies=[Depends(get_current_admin)]
)

MAX_LIMIT = 100


class PublicationOut(BaseModel):
    id: UUID
    published_at: datetime
    theme_id: UUID
    theme_name: str
    channel_title: str
    # Ссылка на сообщение в Telegram собирается на фронте: у приватного канала
    # это t.me/c/<id без префикса -100>/<message_id>.
    channel_tg_chat_id: int
    tg_message_id: int
    # candidate — рерайт чужого поста, pool — пост из собственного запаса
    kind: str
    is_ad_cover: bool
    text: str

    # Только для kind=candidate: откуда пост взялся и чем его переписали.
    # candidate_id нужен, чтобы открыть паспорт поста — «почему вышел именно
    # такой»; у постов из собственного запаса кандидата нет и кнопки не будет.
    candidate_id: UUID | None = None
    source_channel_id: UUID | None = None
    source_channel_title: str | None = None
    source_channel_username: str | None = None
    source_channel_active: bool | None = None
    raw_text: str | None = None
    score: float | None = None
    persona_prompt_used: str | None = None
    # Подтема, к которой отнесён пост. None — рубрик у темы нет или пост вышел
    # до того, как их включили.
    rubric: str | None = None

    views: int | None = None
    forwards: int | None = None


class PublicationsOut(BaseModel):
    items: list[PublicationOut]
    # Есть ли что грузить дальше — чтобы панель показывала «Показать ещё»
    # только когда это осмысленно.
    has_more: bool


@router.get("", response_model=PublicationsOut)
async def list_publications(
    theme_id: UUID | None = None,
    source_channel_id: UUID | None = None,
    days: int | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> PublicationsOut:
    limit = max(1, min(limit, MAX_LIMIT))

    # Последний снапшот метрик на публикацию — тем же коррелированным
    # подзапросом, что и на дашборде (interfaces/api/routers/dashboard.py).
    latest = (
        select(
            PublicationMetricsSnapshot.publication_id,
            func.max(PublicationMetricsSnapshot.taken_at).label("latest_at"),
        )
        .group_by(PublicationMetricsSnapshot.publication_id)
        .subquery()
    )

    stmt = (
        select(
            Publication,
            Theme.id,
            Theme.name,
            TargetChannel.title,
            TargetChannel.tg_chat_id,
            PostVersion.rewritten_text,
            PostVersion.persona_prompt_used,
            PoolPost.text,
            CandidatePost.id,
            CandidatePost.raw_text,
            CandidatePost.score,
            CandidatePost.rubric,
            SourceChannel.id,
            SourceChannel.title,
            SourceChannel.tg_username,
            SourceChannel.is_active,
            PublicationMetricsSnapshot.views,
            PublicationMetricsSnapshot.forwards,
        )
        .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
        .join(Theme, Theme.id == TargetChannel.theme_id)
        .outerjoin(PostVersion, PostVersion.id == Publication.post_version_id)
        .outerjoin(CandidatePost, CandidatePost.id == PostVersion.candidate_post_id)
        .outerjoin(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .outerjoin(PoolPost, PoolPost.id == Publication.pool_post_id)
        .outerjoin(latest, latest.c.publication_id == Publication.id)
        .outerjoin(
            PublicationMetricsSnapshot,
            (PublicationMetricsSnapshot.publication_id == Publication.id)
            & (PublicationMetricsSnapshot.taken_at == latest.c.latest_at),
        )
        .order_by(Publication.published_at.desc())
    )

    if theme_id is not None:
        stmt = stmt.where(Theme.id == theme_id)
    if source_channel_id is not None:
        stmt = stmt.where(SourceChannel.id == source_channel_id)
    if days is not None:
        stmt = stmt.where(Publication.published_at >= datetime.now(timezone.utc) - timedelta(days=days))

    # limit+1, чтобы отличить «ровно столько» от «есть ещё» без второго COUNT.
    rows = (await session.execute(stmt.offset(offset).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        PublicationOut(
            id=pub.id,
            published_at=pub.published_at,
            theme_id=th_id,
            theme_name=th_name,
            channel_title=ch_title,
            channel_tg_chat_id=ch_chat_id,
            tg_message_id=pub.tg_message_id,
            kind="pool" if pub.source is PublicationSource.POOL else "candidate",
            is_ad_cover=pub.is_ad_cover,
            text=(rewritten or pool_text or ""),
            candidate_id=cand_id,
            source_channel_id=src_id,
            source_channel_title=src_title,
            source_channel_username=src_username,
            source_channel_active=src_active,
            raw_text=raw_text,
            score=score,
            persona_prompt_used=persona or None,
            rubric=rubric,
            views=views,
            forwards=forwards,
        )
        for (
            pub, th_id, th_name, ch_title, ch_chat_id, rewritten, persona, pool_text,
            cand_id, raw_text, score, rubric, src_id, src_title, src_username, src_active,
            views, forwards,
        ) in rows
    ]
    return PublicationsOut(items=items, has_more=has_more)


class LearnResult(BaseModel):
    learned: bool
    detail: str


@router.post("/{publication_id}/learn", response_model=LearnResult)
async def learn_from_publication(
    publication_id: UUID, session: AsyncSession = Depends(get_db)
) -> LearnResult:
    """«Этот пост — в персону»: удачный вышедший текст становится образцом
    «пиши так» для бота темы. Обратная связь после публикации раньше вообще
    никуда не возвращалась — оператор видел, что пост зашёл, и не мог ничего
    с этим сделать."""
    row = (
        await session.execute(
            select(Publication, TargetChannel.theme_id, PostVersion.rewritten_text, PoolPost.text)
            .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
            .outerjoin(PostVersion, PostVersion.id == Publication.post_version_id)
            .outerjoin(PoolPost, PoolPost.id == Publication.pool_post_id)
            .where(Publication.id == publication_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    _pub, theme_id, rewritten, pool_text = row
    text = (rewritten or pool_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="У публикации не сохранился текст")

    learned = await remember_good_example(session, theme_id, text)
    if not learned:
        raise HTTPException(
            status_code=400,
            detail="У темы нет бота — учить некого. Создайте бота во вкладке темы",
        )
    await session.commit()
    return LearnResult(learned=True, detail="Пост добавлен в образцы стиля бота темы")
