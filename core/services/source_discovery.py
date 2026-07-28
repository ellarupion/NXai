"""Поиск каналов-источников под тему: LLM подбирает запросы, Telegram отдаёт
кандидатов, мы фильтруем по живости.

Зачем отдельным сервисом. Раньше подбор источников был ручной работой «найди
в поиске, посмотри глазами, вставь @username», и она упиралась в две вещи.
Первая: глобальный поиск Telegram ищет по НАЗВАНИЮ, а ниша в названии почти
никогда не отражена — по запросу «мужская психология» находятся женские
каналы про отношения, а нужные не находятся вовсе. Вторая: даже найдя канал,
нельзя понять, живой ли он, не открыв руками.

Поэтому здесь два источника кандидатов, и второй важнее:

  * поиск по ключевым словам — берёт очевидное, работает всегда;
  * РЕКОМЕНДАЦИИ Telegram к уже добавленным источникам — движок строит их по
    пересечению аудиторий, а не по словам, и вытаскивает ровно соседей по
    нише. Именно он находит то, что поиск не видит.

Оба дают сырой список, который прогоняется через проверку активности:
последний пост, темп публикаций, размер. Мёртвое и пустое отсекается здесь,
чтобы оператору не приходилось открывать каждый канал руками.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient, functions
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from core.config import Settings
from core.llm.client import CLASSIFICATION_MODEL, LLMClient
from core.logging import get_logger
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole
from core.models.source_channel import SourceChannel
from core.models.telethon_session import TelethonSession
from core.models.theme import Theme

logger = get_logger(__name__)

# Границы работы. Telegram быстро отвечает FloodWait на серию запросов, а
# оператор ждёт ответа в браузере — поэтому объём ограничен так, чтобы поиск
# укладывался примерно в полминуты.
MAX_QUERIES = 8
SEARCH_LIMIT = 20
MAX_CHECKED = 40
MAX_RESULTS = 30
SEARCH_PAUSE = 1.0
CHECK_PAUSE = 0.4
ACTIVITY_SAMPLE = 12

DEFAULT_MAX_DAYS_SILENT = 7


class DiscoveryError(Exception):
    """Текст уходит в панель как есть."""


@dataclass(frozen=True)
class ChannelCandidate:
    username: str
    title: str
    about: str
    participants: int | None
    posts_per_day: float
    days_since_last_post: int
    # Как нашли — оператору полезно: «похож на ваш источник» весит больше,
    # чем «совпало слово в названии».
    found_via: str
    already_added: bool


async def suggest_queries(session: AsyncSession, theme_id: UUID) -> list[str]:
    """LLM превращает тему в поисковые запросы.

    Смысл не в том, чтобы придумать синонимы названия темы, а в том, чтобы
    угадать, КАК такие каналы называют себя сами — обычно это не термин из
    ниши, а её сленг и обещание аудитории."""
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise DiscoveryError("Тема не найдена")

    sources = (
        await session.execute(
            select(SourceChannel.title).where(SourceChannel.theme_id == theme_id).limit(15)
        )
    ).scalars().all()
    persona = await session.scalar(
        select(ChannelBot.persona_prompt).where(
            ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
        )
    )

    context = [f"Название темы: {theme.name}"]
    if theme.default_style_prompt:
        context.append(f"Стиль темы: {theme.default_style_prompt[:400]}")
    if persona:
        context.append(f"Персона бота: {persona[:400]}")
    if sources:
        context.append("Уже добавленные источники: " + ", ".join(sources))

    system = (
        "Ты подбираешь поисковые запросы для поиска Telegram-каналов по нише. "
        "Каналы редко называют себя термином из ниши — они называют себя тем, "
        "что обещают аудитории, часто сленгом. Дай запросы, по которым такие "
        "каналы реально находятся в поиске Telegram по названию.\n\n"
        "Правила: от 6 до 8 запросов; каждый 1-3 слова; без кавычек, решёток и "
        "пояснений; на языке ниши; разной степени общности — от узких к широким.\n"
        "Ответ — ТОЛЬКО JSON-массив строк, без markdown и комментариев."
    )
    try:
        result = await _complete_queries(await _settings_for(session), system, context)
    except DiscoveryError:
        raise
    except Exception as exc:
        logger.warning("discovery.llm_failed", error=type(exc).__name__)
        raise DiscoveryError(
            "ИИ не ответил — проверьте ключ Anthropic в «Настройках». "
            "Запросы можно задать и вручную"
        ) from exc

    queries = _parse_queries(result.text)
    if not queries:
        raise DiscoveryError("Не удалось подобрать запросы — попробуйте ещё раз или задайте свои")
    return queries[:MAX_QUERIES]


async def _complete_queries(settings: Settings, system: str, context: list[str]):
    return await LLMClient(settings).complete(
        model=CLASSIFICATION_MODEL,
        system_prompt=system,
        user_prompt="\n".join(context),
        cache_system_prompt=False,
        max_tokens=400,
    )


def _parse_queries(raw: str) -> list[str]:
    """LLM иногда оборачивает JSON в markdown-блок, несмотря на инструкцию."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        # Фолбэк: построчно — лучше отдать что-то рабочее, чем ошибку.
        return [line.strip(" -–—•\"'") for line in raw.splitlines() if 2 < len(line.strip()) < 60][:MAX_QUERIES]
    if not isinstance(parsed, list):
        return []
    return [str(q).strip() for q in parsed if str(q).strip()]


async def _settings_for(session: AsyncSession) -> Settings:
    # Импорт внутри функции: effective_settings тянет panel_settings, а тот —
    # модели, и на уровне модуля получается цикл.
    from core.services.effective_settings import get_effective_settings

    return await get_effective_settings(session)


async def discover_channels(
    session: AsyncSession,
    theme_id: UUID,
    queries: list[str],
    max_days_silent: int = DEFAULT_MAX_DAYS_SILENT,
) -> list[ChannelCandidate]:
    """Ищет кандидатов и возвращает только живые, отсортированные по темпу."""
    settings = await _settings_for(session)

    telethon_session = (
        await session.execute(
            select(TelethonSession).where(TelethonSession.is_active.is_(True)).limit(1)
        )
    ).scalars().first()
    if telethon_session is None:
        raise DiscoveryError(
            "Нет активного аккаунта-читалки — поиск идёт от его имени. "
            "Подключите аккаунт на вкладке «Аккаунты»"
        )

    known = {
        (u or "").lower()
        for u in (await session.execute(select(SourceChannel.tg_username))).scalars().all()
    }
    seeds = (
        await session.execute(
            select(SourceChannel.tg_username).where(
                SourceChannel.theme_id == theme_id, SourceChannel.tg_username.is_not(None)
            )
        )
    ).scalars().all()

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise DiscoveryError(
            "Не заданы Telegram api_id/api_hash — укажите их в «Настройках», "
            "иначе искать не от чего"
        )

    try:
        # StringSession падает уже на разборе строки, если сессия битая, —
        # поэтому в try и создание клиента, а не только connect().
        client = TelegramClient(
            StringSession(telethon_session.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
    except Exception as exc:
        # Битая сессия/недоступный Telegram — наружу должно уйти объяснение, а
        # не пятисотка: оператор не отличит «аккаунт разлогинили» от «панель
        # сломалась», если увидит только «Внутренняя ошибка».
        logger.warning("discovery.connect_failed", error=type(exc).__name__)
        raise DiscoveryError(
            "Не удалось подключиться аккаунтом-читалкой — возможно, сессия устарела. "
            "Переподключите аккаунт на вкладке «Аккаунты»"
        ) from exc

    try:
        found = await _collect(client, queries[:MAX_QUERIES], seeds)
        if not found:
            raise DiscoveryError(
                "Telegram не вернул ни одного канала. Так бывает, если аккаунт-читалка "
                "временно ограничен за частые запросы — попробуйте через несколько минут"
            )
        return await _filter_alive(client, found, known, max_days_silent)
    finally:
        await client.disconnect()


async def _collect(client: TelegramClient, queries: list[str], seeds: list[str]) -> dict:
    """{username: (chat, как_нашли)}. Рекомендации идут ПЕРВЫМИ и не
    перезаписываются поиском: пометка «похож на ваш источник» точнее."""
    found: dict = {}

    for seed in seeds[:6]:
        try:
            entity = await client.get_entity(seed)
            res = await client(
                functions.channels.GetChannelRecommendationsRequest(channel=entity)
            )
            for chat in res.chats:
                if getattr(chat, "username", None) and getattr(chat, "broadcast", False):
                    found.setdefault(chat.username, (chat, f"похож на @{seed}"))
        except FloodWaitError as exc:
            logger.warning("discovery.flood_wait", seconds=exc.seconds)
            break
        except Exception as exc:
            logger.info("discovery.recommendations_failed", seed=seed, error=type(exc).__name__)
        await asyncio.sleep(SEARCH_PAUSE)

    for query in queries:
        try:
            res = await client(functions.contacts.SearchRequest(q=query, limit=SEARCH_LIMIT))
            for chat in res.chats:
                if getattr(chat, "username", None) and getattr(chat, "broadcast", False):
                    found.setdefault(chat.username, (chat, f"по запросу «{query}»"))
        except FloodWaitError as exc:
            logger.warning("discovery.flood_wait", seconds=exc.seconds)
            break
        except Exception as exc:
            logger.info("discovery.search_failed", query=query, error=type(exc).__name__)
        await asyncio.sleep(SEARCH_PAUSE)

    return found


async def _filter_alive(
    client: TelegramClient, found: dict, known: set, max_days_silent: int
) -> list[ChannelCandidate]:
    now = datetime.now(timezone.utc)
    candidates: list[ChannelCandidate] = []

    # Рекомендации проверяем первыми: если упрёмся в лимит, останутся самые
    # ценные кандидаты, а не случайные совпадения по названию.
    ordered = sorted(found.items(), key=lambda kv: 0 if kv[1][1].startswith("похож") else 1)

    for username, (chat, via) in ordered[:MAX_CHECKED]:
        try:
            messages = await client.get_messages(chat, limit=ACTIVITY_SAMPLE)
        except FloodWaitError as exc:
            logger.warning("discovery.flood_wait", seconds=exc.seconds)
            break
        except Exception:
            continue

        if not messages:
            continue
        days_silent = (now - messages[0].date).days
        if days_silent > max_days_silent:
            continue

        window_days = max((messages[0].date - messages[-1].date).days, 1)
        candidates.append(
            ChannelCandidate(
                username=username,
                title=(chat.title or "")[:120],
                about="",
                participants=getattr(chat, "participants_count", None),
                posts_per_day=round(len(messages) / window_days, 1),
                days_since_last_post=days_silent,
                found_via=via,
                already_added=username.lower() in known,
            )
        )
        await asyncio.sleep(CHECK_PAUSE)

    candidates.sort(key=lambda c: (c.already_added, -c.posts_per_day))
    return candidates[:MAX_RESULTS]
