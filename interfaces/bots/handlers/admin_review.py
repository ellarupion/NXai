"""Модерация постов прямо в личке admin-бота (аудит, п.6.1): карточка поста
с кнопками «Одобрить / Отклонить / Править». Оператор живёт в Telegram, и
одобрять кнопкой в чате быстрее, чем ходить в веб-панель — та остаётся для
настройки, бот для ежедневной рутины. Веб-очередь и бот работают с одними и
теми же PENDING_REVIEW-кандидатами, действие в одном месте видно в другом.

Только для role=ADMIN (bot_role из workflow_data); у тематических ботов
хендлеры тихо не срабатывают."""

from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.db import get_session_factory
from core.logging import get_logger
from core.models.enums import BotRole
from core.services.review import (
    ReviewError,
    approve_candidate,
    edit_candidate_text,
    reject_candidate,
)

logger = get_logger(__name__)

router = Router(name="admin-review")

CB_APPROVE = "rv_ok"
CB_REJECT = "rv_no"
CB_EDIT = "rv_ed"

# Ожидания правки текста: chat_id -> candidate_id. Оператор нажал «Править»,
# следующим сообщением в этот чат приходит новый текст. In-memory: переживать
# рестарт процесса тут не нужно — незавершённая правка просто повторяется
# кнопкой заново.
_pending_edits: dict[int, UUID] = {}

PREVIEW_LIMIT = 3500


def build_review_keyboard(candidate_id: UUID) -> InlineKeyboardMarkup:
    cid = str(candidate_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"{CB_APPROVE}:{cid}"),
                InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"{CB_REJECT}:{cid}"),
            ],
            [InlineKeyboardButton(text="✏️ Править", callback_data=f"{CB_EDIT}:{cid}")],
        ]
    )


def build_review_text(source_title: str, rewritten_text: str, score: float | None) -> str:
    score_line = f" · score {score:.2f}" if score is not None else ""
    preview = rewritten_text[:PREVIEW_LIMIT]
    return f"📝 На одобрении — {source_title}{score_line}\n\n{preview}"


@router.callback_query(F.data.startswith(f"{CB_APPROVE}:"))
async def on_approve(callback: CallbackQuery, bot_role: BotRole) -> None:
    if bot_role is not BotRole.ADMIN:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await approve_candidate(session, candidate_id)
            await session.commit()
        except ReviewError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await _finalize(callback, "✅ Одобрено — уйдёт в публикацию по расписанию.")


@router.callback_query(F.data.startswith(f"{CB_REJECT}:"))
async def on_reject(callback: CallbackQuery, bot_role: BotRole) -> None:
    if bot_role is not BotRole.ADMIN:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await reject_candidate(session, candidate_id)
            await session.commit()
        except ReviewError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await _finalize(callback, "🚫 Отклонено.")


@router.callback_query(F.data.startswith(f"{CB_EDIT}:"))
async def on_edit(callback: CallbackQuery, bot_role: BotRole) -> None:
    if bot_role is not BotRole.ADMIN:
        return
    candidate_id = UUID(callback.data.split(":", 1)[1])
    _pending_edits[callback.message.chat.id] = candidate_id
    await callback.answer()
    await callback.message.answer("Пришлите новый текст поста одним сообщением.")


@router.message(F.text, lambda m: m.chat.id in _pending_edits)
async def on_edit_text(message: Message, bot_role: BotRole) -> None:
    if bot_role is not BotRole.ADMIN:
        return
    candidate_id = _pending_edits.pop(message.chat.id, None)
    if candidate_id is None:
        return
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await edit_candidate_text(session, candidate_id, message.text)
            await session.commit()
        except ReviewError as exc:
            await message.answer(f"Не удалось сохранить: {exc}")
            return
    await message.answer(
        "Текст обновлён. Одобрить обновлённый пост?",
        reply_markup=build_review_keyboard(candidate_id),
    )


async def _finalize(callback: CallbackQuery, note: str) -> None:
    """Убирает кнопки у карточки и дописывает итог, чтобы одну и ту же карточку
    нельзя было обработать дважды и было видно, что уже сделано."""
    await callback.answer()
    try:
        await callback.message.edit_text(f"{callback.message.text}\n\n{note}", reply_markup=None)
    except Exception:
        # Сообщение могло быть слишком старым для edit — не критично.
        await callback.message.answer(note)
