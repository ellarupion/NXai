"""Поиск каналов-источников под тему (core/services/source_discovery.py).

Разделено на два эндпоинта намеренно. Подбор запросов — быстрый вызов LLM,
и его результат оператор должен видеть и иметь возможность поправить ДО
поиска: он знает свою нишу лучше модели. Сам поиск ходит в Telegram
десятками запросов с паузами против FloodWait и занимает десятки секунд —
держать оператора всё это время в неведении, что именно ищется, незачем.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.source_discovery import (
    DEFAULT_MAX_DAYS_SILENT,
    DiscoveryError,
    discover_channels,
    suggest_queries,
)
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/discovery", tags=["discovery"], dependencies=[Depends(get_current_admin)])


class QueriesOut(BaseModel):
    queries: list[str]


@router.post("/{theme_id}/queries", response_model=QueriesOut)
async def build_queries(theme_id: UUID, session: AsyncSession = Depends(get_db)) -> QueriesOut:
    try:
        return QueriesOut(queries=await suggest_queries(session, theme_id))
    except DiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SearchPayload(BaseModel):
    queries: list[str]
    max_days_silent: int = DEFAULT_MAX_DAYS_SILENT


class CandidateOut(BaseModel):
    username: str
    title: str
    participants: int | None
    posts_per_day: float
    days_since_last_post: int
    found_via: str
    already_added: bool


class SearchOut(BaseModel):
    candidates: list[CandidateOut]


@router.post("/{theme_id}/search", response_model=SearchOut)
async def search(
    theme_id: UUID, payload: SearchPayload, session: AsyncSession = Depends(get_db)
) -> SearchOut:
    queries = [q.strip() for q in payload.queries if q.strip()]
    if not queries:
        raise HTTPException(status_code=400, detail="Не задано ни одного запроса")
    try:
        found = await discover_channels(session, theme_id, queries, payload.max_days_silent)
    except DiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SearchOut(candidates=[CandidateOut(**vars(c)) for c in found])
