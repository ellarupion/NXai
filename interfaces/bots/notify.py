"""Отправка карточек на одобрение в admin-бот (аудит, п.6.1). Вызывается из
API после «Сделать посты»: боты-процесс потом ловит нажатия кнопок
(interfaces/bots/handlers/admin_review.py). Само нажатие обрабатывает
поллинг admin-бота, а отправку карточки инициирует API — Bot API позволяет
послать сообщение из любого процесса, знающего токен.

Тихо no-op, если admin-бот не создан или ему ещё не написали /start
(notify_chat_id пуст) — как и остальные уведомления, это вторичный эффект,
он не должен ронять генерацию."""

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole
from interfaces.bots.handlers.admin_review import build_review_keyboard, build_review_text

logger = get_logger(__name__)


async def push_review_cards(session: AsyncSession, cards: list[dict]) -> None:
    """cards: [{candidate_id, source_channel_title, rewritten_text, score}]."""
    if not cards:
        return
    result = await session.execute(
        select(ChannelBot).where(ChannelBot.role == BotRole.ADMIN, ChannelBot.is_active.is_(True))
    )
    admin_bot = result.scalar_one_or_none()
    if admin_bot is None or admin_bot.notify_chat_id is None:
        return

    try:
        async with Bot(token=admin_bot.bot_token) as bot:
            for card in cards:
                await bot.send_message(
                    admin_bot.notify_chat_id,
                    build_review_text(
                        card["source_channel_title"], card["rewritten_text"], card.get("score")
                    ),
                    reply_markup=build_review_keyboard(card["candidate_id"]),
                )
    except Exception:
        logger.exception("bots.push_review_cards_failed")
