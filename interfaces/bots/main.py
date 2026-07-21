"""Multi-bot runner — один процесс поднимает Dispatcher на каждый активный
ChannelBot: и тематические публикующие боты, и единственный admin-бот (см.
core/models/channel_bot.py:BotRole, ARCHITECTURE.md §2). В отличие от NX (два
фиксированных токена — editor + submission — заданных в .env), здесь список
ботов читается из БД при старте процесса: новый бот, добавленный в панели,
подхватывается только после рестарта (тот же компромисс, что runtime secret
override в NX, см. ARCHITECTURE.md §7).

Только long polling (dev / небольшой прод). Webhook на несколько токенов
(отдельный путь на каждый bot_token) — ROADMAP.md Phase 3."""

import asyncio

from aiogram import Bot, Dispatcher
from sqlalchemy import select

from core.config import get_settings
from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.models.channel_bot import ChannelBot
from interfaces.bots.handlers import router

logger = get_logger(__name__)

SUPERVISOR_BACKOFF_INITIAL_SECONDS = 5
SUPERVISOR_BACKOFF_MAX_SECONDS = 300
# Проработал дольше этого — считаем запуск успешным и сбрасываем бэкофф
# (иначе бот, падающий раз в час, докрутил бы паузу до максимума навсегда).
SUPERVISOR_STABLE_UPTIME_SECONDS = 600


async def run_bot(channel_bot: ChannelBot) -> None:
    bot = Bot(token=channel_bot.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    # theme_id доступен хендлерам через workflow_data (aiogram) — например,
    # чтобы ad_watchdog-хендлер не полагался только на chat_id при отладке.
    dispatcher["theme_id"] = channel_bot.theme_id
    dispatcher["bot_role"] = channel_bot.role

    logger.info("bots.polling_started", channel_bot_id=str(channel_bot.id), role=channel_bot.role.value)
    await dispatcher.start_polling(bot)


async def supervise_bot(channel_bot: ChannelBot) -> None:
    """Перезапуск с экспоненциальным бэкоффом: один бот с отозванным токеном
    или сетевой ошибкой не должен ронять весь процесс (и ad watchdog остальных
    тем вместе с ним) — раньше asyncio.gather падал целиком по первому
    исключению."""
    backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
    loop = asyncio.get_event_loop()
    while True:
        started_at = loop.time()
        try:
            await run_bot(channel_bot)
            logger.warning("bots.polling_stopped", channel_bot_id=str(channel_bot.id))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bots.polling_crashed", channel_bot_id=str(channel_bot.id))
        if loop.time() - started_at > SUPERVISOR_STABLE_UPTIME_SECONDS:
            backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
        logger.info(
            "bots.polling_restart_scheduled", channel_bot_id=str(channel_bot.id), backoff_seconds=backoff
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, SUPERVISOR_BACKOFF_MAX_SECONDS)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(ChannelBot).where(ChannelBot.is_active.is_(True)))
        channel_bots = list(result.scalars().all())

    if not channel_bots:
        logger.warning("bots.no_active_bots")
        return

    await asyncio.gather(*(supervise_bot(channel_bot) for channel_bot in channel_bots))


if __name__ == "__main__":
    asyncio.run(main())
