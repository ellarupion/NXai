"""Доверие источнику: вес, которым домножается скор его постов.

Источник, чьи посты стабильно отклоняют, должен опускаться в отборе сам, без того чтобы
оператор вычёркивал каналы руками. Источник, исправно поставляющий годное, — наоборот,
подниматься. Скор считается как «пересылки к медиане канала», домноженные на этот вес,
и сравнивается с порогом отбора (core/services/scoring.py).

История, которую здесь важно помнить. Раньше автоматическое отклонение по таймауту
дозревания тоже понижало доверие — и получилась петля: каждое отклонение опускало вес,
опущенный вес делал порог недостижимым, из-за чего следующий пост тоже отклонялся.
Восемнадцать отклонений — и посту требовалось набрать пятнадцать медиан канала. Тема
замолчала на недели, а в базе лежало 5173 отклонённых поста против 22 опубликованных.

Отсюда два решения, которые нельзя откатывать не подумав:
  * автоматическое отклонение по таймауту доверие НЕ трогает (см. scoring.py) — вес
    двигают только события, в которых есть суждение: ручное отклонение, дубликат,
    удачный рерайт;
  * нижняя граница держится такой, из которой источник способен выбраться, и теперь
    она настраивается в панели, а не правится пересборкой образа.

Событие, а не число. Раньше вызывающий передавал готовую дельту, и три места из
четырёх писали её со знаком минус, а одно — с плюсом. Перепутанный знак поймать было
нечем: система молча начала бы поощрять источники за отклонения. Теперь передаётся
СОБЫТИЕ, а величину и знак определяет этот модуль по настройкам.
"""

import enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.source_channel import SourceChannel
from core.services.automation import AutomationSettings, get_automation

logger = get_logger(__name__)


class TrustEvent(str, enum.Enum):
    """Что случилось с постом источника. Знак и величину смотри в _delta_for."""

    REJECTED = "rejected"      # редактор отклонил пост руками — сильный сигнал
    DUPLICATE = "duplicate"    # источник повторил чужую новость — мягкий сигнал
    SUCCESS = "success"        # пост дошёл до готового рерайта — плюс


def _delta_for(event: TrustEvent, automation: AutomationSettings) -> float:
    if event is TrustEvent.REJECTED:
        return -automation.trust_rejected_penalty
    if event is TrustEvent.DUPLICATE:
        return -automation.trust_duplicate_penalty
    return automation.trust_success_bonus


async def adjust_trust_score(
    session: AsyncSession,
    source_channel_id: UUID,
    event: TrustEvent,
    automation: AutomationSettings | None = None,
) -> None:
    """Двигает вес источника по событию, оставаясь в настроенных границах.

    automation можно передать, если вызывающий уже прочитал настройки: планировщик
    читает их раз за тик, и ходить в базу на каждого кандидата незачем."""
    source_channel = await session.get(SourceChannel, source_channel_id)
    if source_channel is None:
        return

    automation = automation or await get_automation(session)
    delta = _delta_for(event, automation)
    before = source_channel.trust_score
    source_channel.trust_score = max(
        automation.min_trust_score,
        min(automation.max_trust_score, source_channel.trust_score + delta),
    )
    logger.info(
        "trust_score.adjusted",
        source_channel_id=str(source_channel_id),
        event=event.value,
        before=round(before, 3),
        after=round(source_channel.trust_score, 3),
    )
    await session.flush()
