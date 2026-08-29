"""Расходы на ИИ: сколько ушло, на что и сколько осталось до потолка.

Отвечает на два разных вопроса, и оба важны. «Сколько всего» — чтобы понимать порядок
трат. «На что именно» — чтобы понимать, какая кнопка дорогая: без разбивки по разделам
работы владелец видел бы одно число и не мог бы решить, что урезать.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.automation import get_automation
from core.services.llm_budget import get_budget_state
from core.services.llm_usage import (
    summary_by_day,
    summary_by_kind,
    summary_by_model,
    summary_by_theme,
)
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/llm-usage", tags=["llm-usage"], dependencies=[Depends(get_current_admin)])

# Дальше двух месяцев назад смотреть незачем, а запрос на год по таблице, куда пишут
# на каждый вызов модели, стоил бы заметно дороже пользы.
MAX_DAYS = 60


class KindOut(BaseModel):
    kind: str
    title: str
    cost_usd: float
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class DayOut(BaseModel):
    day: date
    cost_usd: float


class ThemeCostOut(BaseModel):
    theme_id: UUID | None
    theme_name: str
    cost_usd: float


class BudgetOut(BaseModel):
    limit_usd: float
    spent_today_usd: float
    # 0, когда потолок выключен: показывать «0% из выключенного лимита» бессмысленно.
    percent: int
    enabled: bool
    exceeded: bool
    near_limit: bool
    warn_percent: int


class UsageOut(BaseModel):
    days: int
    total_usd: float
    budget: BudgetOut
    by_kind: list[KindOut]
    by_day: list[DayOut]
    by_model: list[tuple[str, float]]
    by_theme: list[ThemeCostOut]


@router.get("", response_model=UsageOut)
async def usage(days: int = 30, session: AsyncSession = Depends(get_db)) -> UsageOut:
    days = max(1, min(days, MAX_DAYS))

    by_kind = await summary_by_kind(session, days)
    by_day = await summary_by_day(session, days)
    by_model = await summary_by_model(session, days)

    state = await get_budget_state(session)
    automation = await get_automation(session)

    by_theme = await summary_by_theme(session, days)

    return UsageOut(
        days=days,
        total_usd=round(sum(k.cost_usd for k in by_kind), 4),
        budget=BudgetOut(
            limit_usd=state.limit_usd,
            spent_today_usd=round(state.spent_usd, 4),
            percent=state.percent,
            enabled=state.enabled,
            exceeded=state.exceeded,
            near_limit=state.near_limit(automation.budget_warn_percent),
            warn_percent=automation.budget_warn_percent,
        ),
        by_kind=[KindOut(**k.__dict__) for k in by_kind],
        by_day=[DayOut(day=d.day, cost_usd=round(d.cost_usd, 4)) for d in by_day],
        by_model=[(title, round(cost, 4)) for title, cost in by_model],
        by_theme=[
            ThemeCostOut(
                theme_id=t.theme_id,
                theme_name=t.theme_name,
                cost_usd=round(t.cost_usd, 4),
            )
            for t in by_theme
        ],
    )
