"""Проверка авторерайтов редактором в личке ТЕМАТИЧЕСКОГО бота-автора:
бот присылает готовый пост с кнопками «Одобрить / Поправить / Отклонить»
(карточку шлёт scheduler после рерайта — interfaces/bots/notify.py:
push_editor_card). «Поправить» принимает исправленный текст, сохраняет его
новой версией поста И запоминает в личности бота (persona_config.examples_good,
few-shot «пиши так») — так бот учится на правках редактора.

Кому слать и кто имеет право жать кнопки, определяет ChannelBot.editor_chat_id
(задаётся в панели). /start в личке тем-бота отвечает chat_id — так редактор
узнаёт, что вписать в поле «ID редактора».

Только для role=THEME; у admin-бота свой аналогичный флоу
(interfaces/bots/handlers/admin_review.py)."""

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session_factory
from core.logging import get_logger
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole
from core.services.review import (
    ReviewError,
    approve_candidate,
    edit_candidate_text,
    reject_candidate,
)

logger = get_logger(__name__)

router = Router(name="editor-review")

CB_APPROVE = "ed_ok"
CB_REJECT = "ed_no"
CB_FIX = "ed_fx"

# Сколько правок редактора бот держит в личности как примеры «пиши так».
MAX_LEARNED_EXAMPLES = 5

# chat_id -> candidate_id: редактор нажал «Поправить», следующее сообщение —
# исправленный текст. In-memory: незавершённая правка после рестарта процесса
# просто повторяется кнопкой заново.
_pending_fixes: dict[int, UUID] = {}

PREVIEW_LIMIT = 3500


def build_editor_keyboard(candidate_id: UUID) -> InlineKeyboardMarkup:
    cid = str(candidate_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"{CB_APPROVE}:{cid}"),
                InlineKeyboardButton(text="✏️ Поправить", callback_data=f"{CB_FIX}:{cid}"),
            ],
            [InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"{CB_REJECT}:{cid}")],
        ]
    )


def build_editor_text(source_title: str, rewritten_text: str, score: float | None) -> str:
    score_line = f" · виральность {score:.2f}" if score is not None else ""
    return f"📝 Пост на проверку — {source_title}{score_line}\n\n{rewritten_text[:PREVIEW_LIMIT]}"


async def _editor_allowed(session: AsyncSession, theme_id, user_id: int) -> bool:
    editor_id = await session.scalar(
        select(ChannelBot.editor_chat_id).where(
            ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
        )
    )
    return editor_id is not None and editor_id == user_id


@router.message(CommandStart())
async def on_start(message: Message, bot_role: BotRole) -> None:
    """Единственный способ узнать chat_id для поля «ID редактора» в панели —
    Bot API не может написать человеку первым."""
    if bot_role is not BotRole.THEME:
        return
    await message.answer(
        f"Ваш ID: {message.chat.id}\n\n"
        "Вставьте его в поле «ID редактора» этого бота в панели (страница «Боты») — "
        "и бот начнёт присылать сюда готовые посты на проверку."
    )


@router.callback_query(F.data.startswith(f"{CB_APPROVE}:"))
async def on_approve(callback: CallbackQuery, bot_role: BotRole, theme_id) -> None:
    if bot_role is not BotRole.THEME:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    session_factory = get_session_factory()
    async with session_factory() as session:
        if not await _editor_allowed(session, theme_id, callback.from_user.id):
            await callback.answer("Кнопки доступны только редактору этого бота", show_alert=True)
            return
        try:
            await approve_candidate(session, candidate_id)
            await session.commit()
        except ReviewError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await _finalize(callback, "✅ Одобрено.")


@router.callback_query(F.data.startswith(f"{CB_REJECT}:"))
async def on_reject(callback: CallbackQuery, bot_role: BotRole, theme_id) -> None:
    if bot_role is not BotRole.THEME:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    session_factory = get_session_factory()
    async with session_factory() as session:
        if not await _editor_allowed(session, theme_id, callback.from_user.id):
            await callback.answer("Кнопки доступны только редактору этого бота", show_alert=True)
            return
        try:
            await reject_candidate(session, candidate_id)
            await session.commit()
        except ReviewError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await _finalize(callback, "🚫 Отклонено.")


@router.callback_query(F.data.startswith(f"{CB_FIX}:"))
async def on_fix(callback: CallbackQuery, bot_role: BotRole, theme_id) -> None:
    if bot_role is not BotRole.THEME:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    session_factory = get_session_factory()
    async with session_factory() as session:
        if not await _editor_allowed(session, theme_id, callback.from_user.id):
            await callback.answer("Кнопки доступны только редактору этого бота", show_alert=True)
            return
    _pending_fixes[callback.message.chat.id] = candidate_id
    await callback.answer()
    await callback.message.answer(
        "Пришлите исправленный текст одним сообщением — я сохраню его и запомню "
        "вашу правку как образец стиля."
    )


async def _learn_from_fix(session: AsyncSession, theme_id, fixed_text: str) -> None:
    """Запоминание правки в личности: исправленный редактором текст становится
    few-shot примером «пиши так» (persona_config.examples_good, новые вытесняют
    старые, максимум MAX_LEARNED_EXAMPLES) — компилятор персоны
    (core/services/persona.py) подставит его в следующие рерайты."""
    bot = await session.scalar(
        select(ChannelBot).where(ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME)
    )
    if bot is None:
        return
    config = dict(bot.persona_config or {})
    examples = [e for e in (config.get("examples_good") or []) if e != fixed_text]
    examples.append(fixed_text)
    config["examples_good"] = examples[-MAX_LEARNED_EXAMPLES:]
    bot.persona_config = config


@router.message(F.text, lambda m: m.chat.id in _pending_fixes)
async def on_fix_text(message: Message, bot_role: BotRole, theme_id) -> None:
    if bot_role is not BotRole.THEME:
        return
    candidate_id = _pending_fixes.pop(message.chat.id, None)
    if candidate_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        if not await _editor_allowed(session, theme_id, message.from_user.id):
            return
        try:
            await edit_candidate_text(session, candidate_id, message.text)
            await _learn_from_fix(session, theme_id, message.text.strip())
            await session.commit()
        except ReviewError as exc:
            await message.answer(f"Не удалось сохранить: {exc}")
            return
    await message.answer(
        "Сохранил и запомнил правку как образец стиля. Одобрить пост в таком виде?",
        reply_markup=build_editor_keyboard(candidate_id),
    )


async def _finalize(callback: CallbackQuery, note: str) -> None:
    """Убирает кнопки, чтобы карточку нельзя было обработать дважды."""
    await callback.answer()
    try:
        if callback.message.text is not None:
            await callback.message.edit_text(f"{callback.message.text}\n\n{note}", reply_markup=None)
        else:  # карточка с фото — текст лежит в caption
            await callback.message.edit_caption(
                caption=f"{callback.message.caption or ''}\n\n{note}", reply_markup=None
            )
    except Exception:
        await callback.message.answer(note)
