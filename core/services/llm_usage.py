"""Учёт расходов на ИИ: запись каждого вызова и сводки для панели.

До этого модуля токены считались в клиенте и выбрасывались. Ответить на вопрос
«сколько ушло за вчера и на что» было нечем, и когда планировщик без ограничителей
ушёл в непрерывный рерайт, узнали об этом по счёту от провайдера, а не из панели.

Записывать расход обязан ВЫЗЫВАЮЩИЙ, а не LLMClient: клиент про базу ничего не знает
и знать не должен (он тонкая обёртка над провайдером и живёт в core/llm/). Зато
record_usage вызывается ровно там, где известны и раздел работы, и тема, и сущность,
которой этот расход принадлежит.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import CompletionResult
from core.llm.pricing import model_title, usage_cost_usd
from core.logging import get_logger
from core.models.enums import LlmUsageKind
from core.models.llm_usage import LlmUsage

logger = get_logger(__name__)

# Человеческие названия разделов — панель показывает их, а не значения перечисления.
KIND_TITLES: dict[LlmUsageKind, str] = {
    LlmUsageKind.REWRITE: "Рерайт постов",
    LlmUsageKind.CLASSIFY_RUBRIC: "Разбор по подтемам",
    LlmUsageKind.SUGGEST_RUBRICS: "Подбор подтем",
    LlmUsageKind.DISCOVERY: "Поиск источников",
    LlmUsageKind.DIGEST: "Дайджест дня",
    LlmUsageKind.STYLE_EXTRACT: "Разбор стиля канала",
    LlmUsageKind.PERSONA_PREVIEW: "Проба персоны",
    LlmUsageKind.ASSISTANT: "Вопросы помощнику",
}


@dataclass(frozen=True)
class UsageRecord:
    """Один оплаченный вызов в виде, переживающем откат транзакции.

    Строка LlmUsage живёт в сессии и вместе с сессией откатывается. А деньги провайдер
    списал в момент вызова, и откатить их нечем: если рерайт сорвался на классификации
    подтемы, сам рерайт уже оплачен. Такой расход не попал бы ни в отчёт, ни в дневной
    лимит — то есть чем чаще система сбоит, тем дешевле она выглядит.

    Поэтому конвейеры, у которых есть шанс откатиться на середине, собирают не строки,
    а вот такие снимки: их можно записать заново в чистой сессии после отката."""

    kind: LlmUsageKind
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    entity_id: UUID | None
    theme_id: UUID | None


def snapshot(
    result: CompletionResult,
    *,
    kind: LlmUsageKind,
    model: str,
    entity_id: UUID | None = None,
    theme_id: UUID | None = None,
) -> UsageRecord:
    """Считает стоимость вызова и возвращает снимок, ещё ничего не записывая."""
    return UsageRecord(
        kind=kind,
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_write_tokens=result.cache_write_tokens,
        cost_usd=usage_cost_usd(
            model,
            result.input_tokens,
            result.output_tokens,
            result.cache_read_tokens,
            result.cache_write_tokens,
        ),
        entity_id=entity_id,
        theme_id=theme_id,
    )


async def record_usage(
    session: AsyncSession,
    result: CompletionResult,
    *,
    kind: LlmUsageKind,
    model: str,
    entity_id: UUID | None = None,
    theme_id: UUID | None = None,
) -> UsageRecord:
    """Записывает расход в текущую сессию и возвращает снимок.

    Снимок возвращается даже когда запись прошла: вызывающий может держать его на
    случай отката и переписать потом (см. write_snapshots)."""
    record = snapshot(result, kind=kind, model=model, entity_id=entity_id, theme_id=theme_id)
    session.add(_to_row(record))
    return record


async def write_snapshots(session: AsyncSession, records: list[UsageRecord]) -> None:
    """Записывает снимки расходов заново — после отката, в чистой сессии."""
    for record in records:
        session.add(_to_row(record))
    await session.flush()


def _to_row(record: UsageRecord) -> LlmUsage:
    return LlmUsage(
        kind=record.kind,
        model=record.model,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cache_read_tokens=record.cache_read_tokens,
        cache_write_tokens=record.cache_write_tokens,
        cost_usd=record.cost_usd,
        entity_id=record.entity_id,
        theme_id=record.theme_id,
    )


async def spent_since(session: AsyncSession, since: datetime) -> float:
    total = await session.scalar(
        select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0)).where(LlmUsage.created_at >= since)
    )
    return float(total or 0.0)


async def spent_today_usd(session: AsyncSession) -> float:
    """Потрачено с начала суток в таймзоне проекта.

    Именно в таймзоне проекта, а не в UTC: дневной лимит должен обнуляться в полночь
    у оператора. По UTC он у московского владельца сбрасывался бы в три часа ночи,
    и «дневной» расход к вечеру считался бы за неполные сутки."""
    from core.services.panel_settings import get_or_create_panel_settings
    from core.services.scheduler_pool import resolve_zoneinfo

    settings = await get_or_create_panel_settings(session)
    tz = resolve_zoneinfo(settings.timezone)
    local_now = datetime.now(timezone.utc).astimezone(tz)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return await spent_since(session, day_start.astimezone(timezone.utc))


@dataclass(frozen=True)
class KindTotal:
    kind: str
    title: str
    cost_usd: float
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


@dataclass(frozen=True)
class DayTotal:
    day: str
    cost_usd: float


async def summary_by_kind(session: AsyncSession, days: int) -> list[KindTotal]:
    """Разбивка расходов по разделам работы — отвечает на вопрос «какая кнопка дорогая»."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                LlmUsage.kind,
                func.sum(LlmUsage.cost_usd),
                func.count(),
                func.sum(LlmUsage.input_tokens),
                func.sum(LlmUsage.output_tokens),
                func.sum(LlmUsage.cache_read_tokens),
            )
            .where(LlmUsage.created_at >= since)
            .group_by(LlmUsage.kind)
            .order_by(func.sum(LlmUsage.cost_usd).desc())
        )
    ).all()
    return [
        KindTotal(
            kind=kind.value,
            title=KIND_TITLES.get(kind, kind.value),
            cost_usd=float(cost or 0.0),
            calls=int(calls or 0),
            input_tokens=int(inp or 0),
            output_tokens=int(out or 0),
            cache_read_tokens=int(cached or 0),
        )
        for kind, cost, calls, inp, out, cached in rows
    ]


async def summary_by_day(session: AsyncSession, days: int) -> list[DayTotal]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(func.date(LlmUsage.created_at), func.sum(LlmUsage.cost_usd))
            .where(LlmUsage.created_at >= since)
            .group_by(func.date(LlmUsage.created_at))
            .order_by(func.date(LlmUsage.created_at))
        )
    ).all()
    return [DayTotal(day=str(day), cost_usd=float(cost or 0.0)) for day, cost in rows]


@dataclass(frozen=True)
class ThemeTotal:
    theme_id: UUID | None
    theme_name: str
    cost_usd: float


async def summary_by_theme(session: AsyncSession, days: int) -> list[ThemeTotal]:
    """Разбивка по темам — у NXai их несколько, и общий итог не отвечает на вопрос
    «какая тема столько ест».

    Тему берём внешним соединением: расход мог остаться от удалённой темы, и терять
    его из итога нельзя — иначе сумма по темам не сойдётся с общей.

    Период здесь обязателен. Сначала этот запрос жил прямо в роутере и считал за всё
    время, хотя страница была подписана «за 7 дней»: разбивка по темам показывала
    суммы больше общего итога, и сверить одно с другим было невозможно."""
    from core.models.theme import Theme

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(LlmUsage.theme_id, Theme.name, func.sum(LlmUsage.cost_usd))
            .outerjoin(Theme, Theme.id == LlmUsage.theme_id)
            .where(LlmUsage.created_at >= since)
            .group_by(LlmUsage.theme_id, Theme.name)
            .order_by(func.sum(LlmUsage.cost_usd).desc())
        )
    ).all()
    return [
        ThemeTotal(
            theme_id=theme_id,
            theme_name=name or ("удалённая тема" if theme_id else "вне темы"),
            cost_usd=float(cost or 0.0),
        )
        for theme_id, name, cost in rows
    ]


async def summary_by_model(session: AsyncSession, days: int) -> list[tuple[str, float]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(LlmUsage.model, func.sum(LlmUsage.cost_usd))
            .where(LlmUsage.created_at >= since)
            .group_by(LlmUsage.model)
            .order_by(func.sum(LlmUsage.cost_usd).desc())
        )
    ).all()
    return [(model_title(model), float(cost or 0.0)) for model, cost in rows]


async def spent_on_entity(session: AsyncSession, entity_id: UUID) -> tuple[float, list[KindTotal]]:
    """Сколько стоил один конкретный пост и на что именно.

    Считаем запросом, а не храним рядом с постом: расход уже подписан идентификатором
    кандидата в момент вызова модели, и второе место для того же числа рано или поздно
    разъедется с первым."""
    rows = (
        await session.execute(
            select(
                LlmUsage.kind,
                func.sum(LlmUsage.cost_usd),
                func.count(),
                func.sum(LlmUsage.input_tokens),
                func.sum(LlmUsage.output_tokens),
                func.sum(LlmUsage.cache_read_tokens),
            )
            .where(LlmUsage.entity_id == entity_id)
            .group_by(LlmUsage.kind)
            .order_by(func.sum(LlmUsage.cost_usd).desc())
        )
    ).all()
    totals = [
        KindTotal(
            kind=kind.value,
            title=KIND_TITLES.get(kind, kind.value),
            cost_usd=float(cost or 0.0),
            calls=int(calls or 0),
            input_tokens=int(inp or 0),
            output_tokens=int(out or 0),
            cache_read_tokens=int(cached or 0),
        )
        for kind, cost, calls, inp, out, cached in rows
    ]
    return sum(t.cost_usd for t in totals), totals
