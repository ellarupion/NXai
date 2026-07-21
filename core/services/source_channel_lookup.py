"""Резолв @username/ссылки чужого канала в (chat_id, title, username) через
один из Telethon-сессий пула — используется при добавлении нового
source_channel из панели. Заодно подписывает эту сессию на канал: чтение
чужого канала обычным юзер-аккаунтом требует, чтобы аккаунт реально был на
него подписан, иначе live-апдейты (events.NewMessage в
interfaces/telethon_workers/main.py) по этому чату просто не приходят — резолв
имени без подписки был бы бесполезен для ingest (см. ARCHITECTURE.md §7).

chat_id считается через telethon.utils.get_peer_id, а не entity.id напрямую:
для каналов это разные числа (get_peer_id даёt "маркированный" -100xxxxxxxxxx
формат) — он должен совпадать с тем, что реально приходит в
event.chat_id у events.NewMessage, иначе ingest не свяжет живой апдейт с этим
SourceChannel."""

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.utils import get_peer_id

from core.config import Settings
from core.logging import get_logger

logger = get_logger(__name__)


class SourceChannelLookupError(Exception):
    """Текст уходит в HTTP-ответ панели как есть."""


async def resolve_and_join(
    session_string: str, settings: Settings, username_or_link: str
) -> tuple[int, str, str | None]:
    """Возвращает (tg_chat_id, title, tg_username)."""
    client = TelegramClient(StringSession(session_string), settings.telegram_api_id, settings.telegram_api_hash)
    try:
        await client.connect()
        entity = await client.get_entity(username_or_link)
    except Exception as exc:
        await client.disconnect()
        logger.warning("source_channel_lookup.resolve_failed", error=str(exc))
        raise SourceChannelLookupError(f"Не удалось найти канал: {exc}") from exc

    try:
        await client(JoinChannelRequest(entity))
    except Exception as exc:
        # Приватный канал без публичного join'а, уже подписаны и т.п. — не
        # фатально для резолва: chat_id/title у нас уже есть, но ingest не
        # получит live-апдейты, пока аккаунт не окажется в канале вручную
        # (см. докстринг модуля) — сообщаем оператору, но не прерываем добавление.
        logger.warning("source_channel_lookup.join_failed", error=str(exc))

    await client.disconnect()

    chat_id = get_peer_id(entity)
    username = getattr(entity, "username", None)
    title = getattr(entity, "title", None) or username or str(chat_id)
    return chat_id, title, username
