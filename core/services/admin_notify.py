"""Форматирование уведомлений для admin-бота (см. ARCHITECTURE.md §2: один
агрегирующий бот получает события всех тематических ботов). Чистые функции
форматирования — тестируются без БД/aiogram, тот же паттерн, что
format_daily_report в NX core/services/analytics.py. Фактическая отправка
(bot.send_message на admin ChannelBot.bot_token) — в interfaces/bots/main.py,
core/ ничего не знает про aiogram Dispatcher."""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class PublishedNotification:
    theme_name: str
    target_channel_title: str
    preview_text: str


@dataclass(frozen=True)
class AdCoveredNotification:
    theme_name: str
    target_channel_title: str
    covering_preview_text: str


def format_published(notification: PublishedNotification) -> str:
    preview = escape(" ".join(notification.preview_text.split())[:120])
    return (
        f"✅ <b>{escape(notification.theme_name)}</b> → {escape(notification.target_channel_title)}\n"
        f"{preview}"
    )


def format_ad_covered(notification: AdCoveredNotification) -> str:
    preview = escape(" ".join(notification.covering_preview_text.split())[:120])
    return (
        f"🛡 Реклама в «{escape(notification.target_channel_title)}» ({escape(notification.theme_name)}) "
        f"перекрыта своим постом через 60 минут:\n{preview}"
    )


def format_error(theme_name: str, context: str, error: str) -> str:
    return f"⚠️ <b>{escape(theme_name)}</b>: ошибка в {escape(context)}\n<code>{escape(error)}</code>"
