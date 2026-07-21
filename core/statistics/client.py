"""SourceStatsClient — MTProto-чтение чужих каналов через Telethon (адаптировано
из NX core/statistics/client.py:StatsClient). Отличие от NX: там была ровно одна
session_string на весь процесс (только для метрик СВОИХ публикаций); здесь
session_string передаётся явно в конструктор, потому что читающих аккаунтов
несколько (core/models/telethon_session.py — пул, шардинг каналов по
ARCHITECTURE.md §7), и один и тот же класс используют и ingest-воркер (живое
чтение + докачка истории source_channels), и scorer (переопрос views/forwards
чужих кандидатов на контрольных точках).

Строго read-only: ничего не публикует, не пишет, не вступает в чаты. Аккаунт
должен быть подписан на канал, чью историю тут читают — иначе Telethon не
разрешит chat_id/username в сущность."""

from dataclasses import dataclass
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from core.config import Settings, get_settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PostStats:
    views: int | None
    forwards: int | None


@dataclass(frozen=True)
class ChannelHistoryMessage:
    tg_message_id: int
    text: str | None
    grouped_id: int | None
    views: int | None
    forwards: int | None
    # Дата публикации в самом Telegram (не момент, когда мы пост увидели) —
    # нужна докачке: у старого поста forwards накоплены за всю его жизнь, и
    # сравнивать их с "форвардами за первые часы" свежих постов нечестно
    # (core/services/backfill.py решает по этой дате, скорить ли пост вообще).
    posted_at: datetime | None


class SourceStatsClient:
    def __init__(self, session_string: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session_string = session_string
        self._client: TelegramClient | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = TelegramClient(
            StringSession(self._session_string),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )
        await self._client.connect()
        logger.info("source_stats_client.connected")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
            logger.info("source_stats_client.disconnected")

    async def get_post_stats(self, chat_id: int, message_id: int) -> PostStats | None:
        if self._client is None:
            raise RuntimeError("SourceStatsClient не подключён — вызовите connect() сначала")

        message = await self._client.get_messages(chat_id, ids=message_id)
        if message is None:
            return None
        return PostStats(views=message.views, forwards=message.forwards)

    async def get_messages_after(
        self, chat_id: int, min_id: int, limit: int = 500
    ) -> list[ChannelHistoryMessage]:
        """История канала строго после min_id — используется и для живой докачки
        (SourceChannel.last_scanned_message_id), и на будущее для повторного
        сканирования после простоя ingest-воркера, тот же контракт, что backfill в NX."""
        if self._client is None:
            raise RuntimeError("SourceStatsClient не подключён — вызовите connect() сначала")

        messages: list[ChannelHistoryMessage] = []
        async for message in self._client.iter_messages(chat_id, min_id=min_id, reverse=True, limit=limit):
            messages.append(self._to_history_message(message))
        return messages

    async def get_recent_messages(self, chat_id: int, limit: int = 30) -> list[ChannelHistoryMessage]:
        """Последние limit сообщений канала (самые свежие). Используется для
        ПЕРВОГО скана нового source_channel: get_messages_after(min_id=0)
        отдал бы 30 СТАРЕЙШИХ постов канала — с годами накопленных forwards,
        которые скоринг принял бы за сверхвиральность (см. аудит, баг К2)."""
        if self._client is None:
            raise RuntimeError("SourceStatsClient не подключён — вызовите connect() сначала")

        messages: list[ChannelHistoryMessage] = []
        async for message in self._client.iter_messages(chat_id, limit=limit):
            messages.append(self._to_history_message(message))
        # iter_messages без reverse отдаёт от новых к старым — разворачиваем,
        # чтобы вызывающая сторона всегда получала хронологический порядок.
        messages.reverse()
        return messages

    @staticmethod
    def _to_history_message(message) -> ChannelHistoryMessage:  # noqa: ANN001 — telethon Message
        return ChannelHistoryMessage(
            tg_message_id=message.id,
            text=message.raw_text or None,
            grouped_id=message.grouped_id,
            views=message.views,
            forwards=message.forwards,
            posted_at=message.date,
        )

    async def __aenter__(self) -> "SourceStatsClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.disconnect()
