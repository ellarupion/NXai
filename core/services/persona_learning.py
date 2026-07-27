"""Дообучение персоны бота на удачных текстах.

Правка редактора в Telegram (interfaces/bots/handlers/editor_review.py) и
кнопка «Эту правку — в персону» на странице «Публикации» делают одно и то же:
кладут текст в persona_config.examples_good, откуда компилятор персоны
(core/services/persona.py) подставит его в следующие рерайты как few-shot
образец «пиши так». Правило «сколько храним и как дедуплицируем» должно быть
одно на оба входа, поэтому живёт здесь, а не копией в каждом месте."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole

# Сколько образцов «пиши так» бот держит в личности. Больше — промпт раздувается
# и начинает переучивать модель на копирование, а не на стиль.
MAX_LEARNED_EXAMPLES = 5


async def remember_good_example(session: AsyncSession, theme_id: UUID, text: str) -> bool:
    """Добавляет текст в примеры «пиши так» у тематического бота.

    Возвращает False, если у темы нет бота (учить некого). Дубликаты не
    копятся: повтор того же текста поднимает его в конец списка, а не
    занимает второй слот."""
    text = text.strip()
    if not text:
        return False

    bot = await session.scalar(
        select(ChannelBot).where(ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME)
    )
    if bot is None:
        return False

    config = dict(bot.persona_config or {})
    examples = [e for e in (config.get("examples_good") or []) if e != text]
    examples.append(text)
    config["examples_good"] = examples[-MAX_LEARNED_EXAMPLES:]
    bot.persona_config = config
    await session.flush()
    return True
