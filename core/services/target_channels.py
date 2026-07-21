"""Регистрация целевого канала темы — тот же паттерн верификации, что
core/services/channels.py в NX (проверка через живой Bot API, что бот реально
админ канала, а не просто вписан оператором вручную), адаптировано под
multi-bot: здесь бот берётся из ChannelBot конкретной темы (role=THEME), а не
один фиксированный на весь процесс."""

from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.target_channel import TargetChannel

logger = get_logger(__name__)

ADMIN_STATUSES = {"administrator", "creator"}


class BotNotAdminError(Exception):
    """Бот не состоит в админах указанного канала — добавление не подтверждено."""


class TargetChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_target_channel(
        self, bot: Bot, theme_id: UUID, chat_id_or_username: int | str, signature: str = ""
    ) -> TargetChannel:
        """Принимает либо числовой tg_chat_id, либо @username канала — сначала
        резолвит через get_chat (даёт канонический числовой id для хранения в
        TargetChannel.tg_chat_id независимо от того, что ввёл оператор), затем
        проверяет через Bot API, что тематический бот реально админ канала."""
        try:
            chat = await bot.get_chat(chat_id_or_username)
        except TelegramAPIError as exc:
            raise BotNotAdminError(f"Не удалось получить чат {chat_id_or_username}: {exc}") from exc

        try:
            member = await bot.get_chat_member(chat.id, bot.id)
        except TelegramAPIError as exc:
            raise BotNotAdminError(f"Не удалось проверить права бота в чате {chat.id}: {exc}") from exc

        if member.status not in ADMIN_STATUSES:
            raise BotNotAdminError(f"Бот не в админах чата {chat.id} (статус: {member.status})")

        tg_chat_id = chat.id
        title = chat.title or str(tg_chat_id)

        existing = await self.get_by_tg_chat_id(tg_chat_id)
        if existing is not None:
            existing.title = title
            existing.theme_id = theme_id
            existing.is_active = True
            if signature:
                existing.signature = signature
            await self.session.flush()
            logger.info("target_channels.reactivated", target_channel_id=str(existing.id))
            return existing

        target_channel = TargetChannel(theme_id=theme_id, tg_chat_id=tg_chat_id, title=title, signature=signature)
        self.session.add(target_channel)
        await self.session.flush()
        logger.info("target_channels.added", target_channel_id=str(target_channel.id), title=title)
        return target_channel

    async def get_by_tg_chat_id(self, tg_chat_id: int) -> TargetChannel | None:
        result = await self.session.execute(select(TargetChannel).where(TargetChannel.tg_chat_id == tg_chat_id))
        return result.scalar_one_or_none()
