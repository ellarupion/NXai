"""Multi-bot runner — один процесс поднимает Dispatcher на каждый активный
ChannelBot: и тематические публикующие боты, и единственный admin-бот (см.
core/models/channel_bot.py:BotRole).

Конфигурация горячо перечитывается (аудит, п.8.3): reconcile-цикл раз в
RELOAD_INTERVAL сверяет активных ботов в БД с запущенными и запускает новых,
останавливает удалённых/выключенных и перезапускает тех, у кого сменился
токен/роль/тема — без рестарта процесса. Раньше список читался только на
старте, и новый бот подхватывался лишь рестартом.

Только long polling (dev / небольшой прод). Webhook на несколько токенов —
ROADMAP.md Phase 3."""

import asyncio

from aiogram import Bot, Dispatcher
from sqlalchemy import select

from core.config import get_settings
from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.models.channel_bot import ChannelBot
from core.services.heartbeat import WORKER_BOTS, record_heartbeat
from interfaces.bots.handlers import router

logger = get_logger(__name__)

SUPERVISOR_BACKOFF_INITIAL_SECONDS = 5
SUPERVISOR_BACKOFF_MAX_SECONDS = 300
# Проработал дольше этого — считаем запуск успешным и сбрасываем бэкофф
# (иначе бот, падающий раз в час, докрутил бы паузу до максимума навсегда).
SUPERVISOR_STABLE_UPTIME_SECONDS = 600
HEARTBEAT_INTERVAL_SECONDS = 60
RELOAD_INTERVAL_SECONDS = 30


async def heartbeat_loop(count_fn) -> None:
    """Бьётся раз в минуту, пока процесс жив — long-polling воркеры не имеют
    «тика», поэтому heartbeat отдельной корутиной (аудит, п.3.1)."""
    while True:
        try:
            await record_heartbeat(WORKER_BOTS, detail=f"{count_fn()} бот(ов)")
        except Exception:
            logger.exception("bots.heartbeat_failed")
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def run_bot(bot_token: str, theme_id, bot_role) -> None:
    bot = Bot(token=bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher["theme_id"] = theme_id
    dispatcher["bot_role"] = bot_role
    logger.info("bots.polling_started", role=bot_role.value)
    await dispatcher.start_polling(bot)


async def supervise_bot(bot_id, bot_token: str, theme_id, bot_role) -> None:
    """Перезапуск одного бота с экспоненциальным бэкоффом — один отозванный
    токен/сетевой сбой не роняет остальных ботов процесса."""
    backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
    loop = asyncio.get_event_loop()
    while True:
        started_at = loop.time()
        try:
            await run_bot(bot_token, theme_id, bot_role)
            logger.warning("bots.polling_stopped", channel_bot_id=str(bot_id))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("bots.polling_crashed", channel_bot_id=str(bot_id))
        if loop.time() - started_at > SUPERVISOR_STABLE_UPTIME_SECONDS:
            backoff = SUPERVISOR_BACKOFF_INITIAL_SECONDS
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, SUPERVISOR_BACKOFF_MAX_SECONDS)


async def _load_bot_configs() -> dict:
    """{bot_id: (signature, token, theme_id, role)} активных ботов. signature
    (token, theme_id, role) — по её смене reconcile перезапускает бота."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(ChannelBot).where(ChannelBot.is_active.is_(True)))
        configs = {}
        for bot in result.scalars().all():
            signature = (bot.bot_token, str(bot.theme_id), bot.role.value)
            configs[bot.id] = (signature, bot.bot_token, bot.theme_id, bot.role)
        return configs


async def reconcile_loop(tasks: dict) -> None:
    """Держит набор запущенных ботов в соответствии с БД (аудит, п.8.3)."""
    signatures: dict = {}
    while True:
        try:
            configs = await _load_bot_configs()
        except Exception:
            logger.exception("bots.reconcile_load_failed")
            await asyncio.sleep(RELOAD_INTERVAL_SECONDS)
            continue

        wanted = set(configs)
        running = set(tasks)

        # Удалённые/выключенные — останавливаем.
        for bot_id in running - wanted:
            tasks.pop(bot_id).cancel()
            signatures.pop(bot_id, None)
            logger.info("bots.stopped_removed", channel_bot_id=str(bot_id))

        for bot_id, (signature, token, theme_id, role) in configs.items():
            if bot_id in tasks and signatures.get(bot_id) == signature:
                continue
            if bot_id in tasks:  # изменился токен/роль/тема — перезапуск
                tasks.pop(bot_id).cancel()
                logger.info("bots.restarting_changed", channel_bot_id=str(bot_id))
            tasks[bot_id] = asyncio.create_task(supervise_bot(bot_id, token, theme_id, role))
            signatures[bot_id] = signature

        await asyncio.sleep(RELOAD_INTERVAL_SECONDS)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    tasks: dict = {}
    await asyncio.gather(
        heartbeat_loop(lambda: len(tasks)),
        reconcile_loop(tasks),
    )


if __name__ == "__main__":
    asyncio.run(main())
