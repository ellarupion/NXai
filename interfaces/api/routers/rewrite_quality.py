"""Замеры качества рерайта: заказать, посмотреть, удалить.

Заказ ничего не считает — считает планировщик (scheduler.py:quality_run_job). Замер
идёт минутами, и держать на нём открытым запрос панели нельзя: браузер отвалится по
таймауту раньше, чем придёт ответ, а деньги к тому моменту уже будут потрачены.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.channel_bot import ChannelBot
from core.models.enums import AuditAction, BotRole
from core.models.rewrite_quality import RewriteQualityPair, RewriteQualityRun
from core.models.theme import Theme
from core.services.audit import record_audit
from core.services.persona import build_persona_prompt
from core.services.rewrite_quality import (
    DEFAULT_SIZE,
    MAX_SIZE,
    MIN_SIZE,
    QualityRunError,
    RewriteQualityService,
    verdict_summary,
)
from interfaces.api.auth import CurrentAdmin, get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/quality-runs", tags=["quality"], dependencies=[Depends(get_current_admin)]
)


class RunOut(BaseModel):
    id: UUID
    theme_id: UUID | None
    theme_name: str | None
    title: str
    status: str
    size: int
    # Сколько пар уже посужено. Нужно идущему замеру: он считается минутами, и
    # строка «идёт прямо сейчас» без продвижения читается как зависание.
    judged: int
    wins_baseline: int
    wins_variant: int
    ties: int
    # Итог словами — его и читает человек. Считается на бэкенде, чтобы решение «как
    # считать ничьи» жило в одном месте, а не в панели вторым экземпляром.
    summary: str
    baseline_model: str
    variant_model: str
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class PairOut(BaseModel):
    id: UUID
    source_text: str
    baseline_text: str
    variant_text: str
    verdict: str | None
    # Оба приговора видны намеренно: разошлись — значит, судья поменял мнение от
    # одной перестановки, и человеку стоит это видеть, а не только итоговую ничью.
    verdict_direct: str | None
    verdict_swapped: str | None
    reason: str


class RunDetailOut(RunOut):
    baseline_persona: str
    variant_persona: str
    pairs: list[PairOut]


class CreateRunRequest(BaseModel):
    theme_id: UUID
    title: str = ""
    # Персона «как сейчас» не присылается: её берём у бота темы сами. Присылать её с
    # клиента значило бы сравнивать с тем, что панель считает текущим, а не с тем,
    # чем система на самом деле пишет.
    variant_persona: str = Field(min_length=1, max_length=20000)
    size: int = Field(default=DEFAULT_SIZE, ge=MIN_SIZE, le=MAX_SIZE)


def _to_run_out(run: RewriteQualityRun, theme_name: str | None, judged: int = 0) -> RunOut:
    return RunOut(
        id=run.id,
        theme_id=run.theme_id,
        theme_name=theme_name,
        title=run.title,
        status=run.status.value,
        size=run.size,
        judged=judged,
        wins_baseline=run.wins_baseline,
        wins_variant=run.wins_variant,
        ties=run.ties,
        summary=verdict_summary(run),
        baseline_model=run.baseline_model,
        variant_model=run.variant_model,
        error=run.error,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.get("", response_model=list[RunOut])
async def list_runs(
    theme_id: UUID | None = None, session: AsyncSession = Depends(get_db)
) -> list[RunOut]:
    stmt = (
        select(RewriteQualityRun, Theme.name)
        .outerjoin(Theme, Theme.id == RewriteQualityRun.theme_id)
        .order_by(RewriteQualityRun.created_at.desc())
        .limit(50)
    )
    if theme_id is not None:
        stmt = stmt.where(RewriteQualityRun.theme_id == theme_id)
    rows = (await session.execute(stmt)).all()

    # Одним запросом на весь список, а не по запросу на замер: страница опрашивается
    # каждые десять секунд, и запрос на строку превратился бы в постоянную нагрузку.
    judged = dict(
        (
            await session.execute(
                select(RewriteQualityPair.run_id, func.count())
                .where(
                    RewriteQualityPair.run_id.in_([run.id for run, _ in rows]),
                    RewriteQualityPair.verdict.is_not(None),
                )
                .group_by(RewriteQualityPair.run_id)
            )
        ).all()
    ) if rows else {}
    return [_to_run_out(run, name, judged.get(run.id, 0)) for run, name in rows]


@router.get("/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_db)) -> RunDetailOut:
    row = (
        await session.execute(
            select(RewriteQualityRun, Theme.name)
            .outerjoin(Theme, Theme.id == RewriteQualityRun.theme_id)
            .where(RewriteQualityRun.id == run_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Замер не найден")
    run, theme_name = row
    pairs = (
        await session.execute(
            select(RewriteQualityPair)
            .where(RewriteQualityPair.run_id == run_id)
            .order_by(RewriteQualityPair.created_at)
        )
    ).scalars().all()
    base = _to_run_out(run, theme_name, sum(1 for p in pairs if p.verdict is not None))
    return RunDetailOut(
        **base.model_dump(),
        baseline_persona=run.baseline_persona,
        variant_persona=run.variant_persona,
        pairs=[
            PairOut(
                id=p.id,
                source_text=p.source_text,
                baseline_text=p.baseline_text,
                variant_text=p.variant_text,
                verdict=p.verdict.value if p.verdict else None,
                verdict_direct=p.verdict_direct.value if p.verdict_direct else None,
                verdict_swapped=p.verdict_swapped.value if p.verdict_swapped else None,
                reason=p.reason,
            )
            for p in pairs
        ],
    )


@router.post("", response_model=RunOut, status_code=201)
async def create_run(
    payload: CreateRunRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentAdmin = Depends(get_current_admin),
) -> RunOut:
    theme = await session.get(Theme, payload.theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Тема не найдена")

    bot = (
        await session.execute(
            select(ChannelBot).where(
                ChannelBot.theme_id == theme.id, ChannelBot.role == BotRole.THEME
            )
        )
    ).scalars().first()
    if bot is None:
        raise HTTPException(
            status_code=400,
            detail="У темы нет бота — сравнивать не с чем: текущая персона живёт у него",
        )
    # Ровно тот промпт, которым тема пишет прямо сейчас: собран той же функцией, что
    # и в конвейере. Иначе «текущий вариант» в замере был бы не тем, что в канале.
    baseline = build_persona_prompt(bot.persona_config, bot.persona_prompt)

    try:
        run = await RewriteQualityService(session).create_run(
            theme_id=theme.id,
            title=payload.title,
            baseline_persona=baseline,
            variant_persona=payload.variant_persona,
            size=payload.size,
        )
    except QualityRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit(
        session,
        AuditAction.SETTINGS_CHANGE,
        "quality_run",
        str(run.id),
        {"field": "замер качества", "size": run.size},
        actor_admin_username=current.username,
        theme_id=theme.id,
    )
    await session.commit()
    return _to_run_out(run, theme.name)


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    run = await session.get(RewriteQualityRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Замер не найден")
    await session.delete(run)
    await session.commit()
