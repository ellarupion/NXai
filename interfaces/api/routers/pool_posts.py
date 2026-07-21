"""CRUD запасного пула темы (core/models/pool_post.py) — evergreen-контент,
используемый и для обычного заполнения расписания (когда пул REWRITTEN-
кандидатов пуст), и для авто-перекрытия рекламы
(core/services/ad_watchdog.py). Наполнение здесь — только ручное
(PoolPostSource.MANUAL); проактивная LLM-генерация evergreen-контента —
ROADMAP.md Phase 4/5."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.enums import PoolPostSource, PoolPostStatus
from core.models.pool_post import PoolPost
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/pool-posts", tags=["pool-posts"], dependencies=[Depends(get_current_admin)])


class PoolPostOut(BaseModel):
    id: UUID
    theme_id: UUID
    text: str
    source: PoolPostSource
    status: PoolPostStatus
    times_used: int

    model_config = {"from_attributes": True}


class PoolPostCreate(BaseModel):
    theme_id: UUID
    text: str


class PoolPostUpdate(BaseModel):
    text: str | None = None
    status: PoolPostStatus | None = None


@router.get("", response_model=list[PoolPostOut])
async def list_pool_posts(
    theme_id: UUID | None = None, session: AsyncSession = Depends(get_db)
) -> list[PoolPost]:
    stmt = select(PoolPost).order_by(PoolPost.created_at.desc())
    if theme_id is not None:
        stmt = stmt.where(PoolPost.theme_id == theme_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=PoolPostOut)
async def create_pool_post(payload: PoolPostCreate, session: AsyncSession = Depends(get_db)) -> PoolPost:
    pool_post = PoolPost(theme_id=payload.theme_id, text=payload.text, source=PoolPostSource.MANUAL)
    session.add(pool_post)
    await session.flush()
    await session.commit()
    return pool_post


@router.put("/{pool_post_id}", response_model=PoolPostOut)
async def update_pool_post(
    pool_post_id: UUID, payload: PoolPostUpdate, session: AsyncSession = Depends(get_db)
) -> PoolPost:
    pool_post = await session.get(PoolPost, pool_post_id)
    if pool_post is None:
        raise HTTPException(status_code=404, detail="PoolPost not found")
    if payload.text is not None:
        pool_post.text = payload.text
    if payload.status is not None:
        pool_post.status = payload.status
    await session.flush()
    await session.commit()
    return pool_post


@router.delete("/{pool_post_id}", status_code=204)
async def delete_pool_post(pool_post_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    pool_post = await session.get(PoolPost, pool_post_id)
    if pool_post is None:
        return
    await session.delete(pool_post)
    await session.commit()
