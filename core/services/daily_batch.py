"""Дневная партия постов: заказ, размер и долг.

Пайплайн был непрерывным конвейером — планировщик каждые пять минут брал
отобранных кандидатов и переписывал их. На теме с дюжиной источников это
десятки постов в сутки, все в «Проверку», и каждый оплачен вызовом LLM.
Оператору столько не нужно, а разобрать столько он не успевает.

Здесь другая модель: партия на день. Оператор просит «Посты на сегодня», тема
готовит ровно столько, сколько он публикует за день, и замолкает. Дальше
работает арифметика долга:

    долг = заказано − (одобрено сегодня + ждёт проверки)

Заказали 5 → пришло 5, долг 0, тишина.
Одобрили все 5 → 5 + 0 = 5, долг 0, тишина.
Отклонили один → 0 + 4 = 4, долг 1 — доедет замена.
Одобрили 4, отклонили 1 → 4 + 0 = 4, долг 1 — тоже замена.

Долг гасит планировщик на ближайшем тике, а не сам запрос на отклонение:
рерайт — это секунды ожидания LLM, и держать на них открытым HTTP-запрос
панели незачем. Оператор отклоняет пост и продолжает разбирать очередь,
замена приходит следом.

«Сегодня» — в таймзоне проекта (PanelSettings.timezone), а не в UTC: у
оператора в Москве день кончается в полночь по Москве.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.channel_bot import DEFAULT_CADENCE, ChannelBot
from core.models.enums import BotRole, CandidatePostStatus
from core.models.source_channel import SourceChannel
from core.models.theme import Theme
from core.services.panel_settings import get_or_create_panel_settings
from core.services.scheduler_pool import resolve_zoneinfo

# Потолок на одну просьбу. Не про деньги (их стережёт лимит планировщика), а
# про человека: партию надо разобрать руками, и полсотни карточек за раз —
# это не помощь.
MAX_DAILY_BATCH = 20


async def today_in_project_tz(session: AsyncSession) -> date:
    settings = await get_or_create_panel_settings(session)
    return datetime.now(timezone.utc).astimezone(resolve_zoneinfo(settings.timezone)).date()


async def daily_target(session: AsyncSession, theme_id: UUID) -> int:
    """Сколько постов в день тема публикует по своему расписанию.

    Берём из кадансa бота, а не спрашиваем число у оператора: он уже задал
    расписание в «Бот и стиль», и просить то же самое второй раз — способ
    развести две настройки, которые обязаны совпадать."""
    cadence = await session.scalar(
        select(ChannelBot.cadence).where(
            ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
        )
    )
    target = int((cadence or DEFAULT_CADENCE).get("posts_per_day_target") or 0)
    return max(1, min(target, MAX_DAILY_BATCH))


async def order_batch(session: AsyncSession, theme: Theme, size: int) -> None:
    """Отмечает, что партия на сегодня заказана. Повторная просьба в тот же
    день НЕ складывается с предыдущей, а заменяет её: «сделай посты на
    сегодня» дважды — это одна просьба, повторённая, а не двойной заказ."""
    theme.daily_batch_date = await today_in_project_tz(session)
    theme.daily_batch_size = size


async def outstanding(session: AsyncSession, theme_id: UUID) -> int:
    """Сколько постов темы ещё должно доехать, чтобы заказ был закрыт.

    Ноль, если на сегодня ничего не заказывали — тема в ручном режиме молчит,
    пока её не попросят."""
    theme = await session.get(Theme, theme_id)
    if theme is None or theme.daily_batch_size <= 0:
        return 0
    if theme.daily_batch_date != await today_in_project_tz(session):
        return 0

    # Считаем ТОЛЬКО посты этой партии. Соблазнительно было бы взять «сколько
    # постов темы одобрено сегодня», но это другое число: тема могла одобрять
    # посты, приготовленные до перехода в ручной режим, и они гасили бы заказ,
    # которого не выполняли. Проверено на живой базе — так и вышло.
    alive = await _count(
        session,
        theme_id,
        [
            CandidatePostStatus.PENDING_REVIEW,
            CandidatePostStatus.REWRITTEN,
            CandidatePostStatus.PUBLISHED,
        ],
        batch_date=theme.daily_batch_date,
    )
    return max(0, theme.daily_batch_size - alive)


async def _count(
    session: AsyncSession,
    theme_id: UUID,
    statuses: list[CandidatePostStatus],
    batch_date: date | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(CandidatePost)
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(SourceChannel.theme_id == theme_id, CandidatePost.status.in_(statuses))
    )
    if batch_date is not None:
        stmt = stmt.where(CandidatePost.batch_date == batch_date)
    return int(await session.scalar(stmt) or 0)
