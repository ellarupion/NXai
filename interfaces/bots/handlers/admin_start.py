"""/start в личке с admin-ботом — единственный способ узнать, куда слать
уведомления: Bot API не может написать первым тому, кто не инициировал
диалог с ботом (см. core/models/channel_bot.py:ChannelBot.notify_chat_id).

Хендлер подключён ко ВСЕМ ботам (interfaces/bots/handlers/__init__.py — тот
же router, что и у тематических), поскольку interfaces/bots/main.py поднимает
один и тот же Dispatcher-router для каждого ChannelBot независимо от роли.
Работает только для role=ADMIN — bot_role приходит через workflow_data
(dispatcher["bot_role"] в interfaces/bots/main.py), у тематических ботов
хендлер тихо не срабатывает."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from core.db import get_session_factory
from core.logging import get_logger
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole

logger = get_logger(__name__)

router = Router(name="admin-start")


@router.message(CommandStart())
async def on_start(message: Message, bot_role: BotRole) -> None:
    if bot_role is not BotRole.ADMIN:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(ChannelBot).where(ChannelBot.role == BotRole.ADMIN))
        channel_bot = result.scalar_one_or_none()
        if channel_bot is None:
            return
        channel_bot.notify_chat_id = message.chat.id
        await session.commit()

    await message.answer("Готово — уведомления по всем темам теперь будут приходить сюда.")
    logger.info("admin_bot.notify_chat_registered", chat_id=message.chat.id)
