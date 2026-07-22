"""CRUD ботов (тематических и admin) — токены живут в БД (core/models/channel_bot.py),
не в .env, поэтому ввод/смена токена — операция панели, а не SSH. gated
require_superadmin целиком: bot_token — секрет уровня прод-инцидента при утечке."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import LLMClient
from core.models.channel_bot import DEFAULT_CADENCE, ChannelBot
from core.models.enums import AuditAction, BotRole
from core.services.audit import record_audit
from core.services.effective_settings import get_effective_settings
from core.services.style_extractor import StyleExtractorError, extract_style
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/channel-bots", tags=["channel-bots"], dependencies=[Depends(require_superadmin)])

# Имена партиал-уникальных индексов из core/models/channel_bot.py — по ним
# отличаем «уже есть активный бот на эту тему» от «уже есть admin-бот», чтобы
# показать оператору осмысленный текст, а не сырой psql-констрейнт.
_ACTIVE_THEME_INDEX = "uq_channel_bots_active_theme"
_ACTIVE_ADMIN_INDEX = "uq_channel_bots_active_admin"


def _uniqueness_message(exc: IntegrityError) -> str:
    detail = str(getattr(exc, "orig", exc))
    if _ACTIVE_THEME_INDEX in detail:
        return "У этой темы уже есть активный бот — отключите старый прежде чем заводить нового"
    if _ACTIVE_ADMIN_INDEX in detail:
        return "Admin-бот уже создан — отредактируйте существующую запись или отключите её"
    return "Нарушено ограничение уникальности бота"


class ChannelBotOut(BaseModel):
    id: UUID
    theme_id: UUID | None
    role: BotRole
    persona_prompt: str
    cadence: dict
    is_active: bool
    token_set: bool
    # Значим только для role=admin — есть ли получатель уведомлений
    # (см. core/models/channel_bot.py:notify_chat_id,
    # interfaces/bots/handlers/admin_start.py). Для role=theme всегда False.
    notify_chat_set: bool

    model_config = {"from_attributes": True}

    @staticmethod
    def from_model(bot: ChannelBot) -> "ChannelBotOut":
        return ChannelBotOut(
            id=bot.id,
            theme_id=bot.theme_id,
            role=bot.role,
            persona_prompt=bot.persona_prompt,
            cadence=bot.cadence,
            is_active=bot.is_active,
            token_set=bool(bot.bot_token),
            notify_chat_set=bot.notify_chat_id is not None,
        )


class ChannelBotCreate(BaseModel):
    theme_id: UUID | None = None
    role: BotRole = BotRole.THEME
    bot_token: str
    persona_prompt: str = ""
    cadence: dict = DEFAULT_CADENCE

    @model_validator(mode="after")
    def _theme_matches_role(self) -> "ChannelBotCreate":
        if self.role == BotRole.THEME and self.theme_id is None:
            raise ValueError("theme_id обязателен для role=theme")
        if self.role == BotRole.ADMIN and self.theme_id is not None:
            raise ValueError("role=admin не привязывается к теме (theme_id должен быть пустым)")
        return self


class ChannelBotUpdate(BaseModel):
    """Все поля опциональны — PUT меняет только переданное. `bot_token=None`
    значит "не менять токен", в отличие от settings.py здесь нет смысла в
    отдельном "сбросить" — без валидного токена бот нерабочий, обнулять
    незачем."""

    bot_token: str | None = None
    persona_prompt: str | None = None
    cadence: dict | None = None
    is_active: bool | None = None
    theme_id: UUID | None = None


class ExtractStyleRequest(BaseModel):
    reference_posts: list[str]


class ExtractStyleResponse(BaseModel):
    suggested_persona: str


@router.get("", response_model=list[ChannelBotOut])
async def list_channel_bots(session: AsyncSession = Depends(get_db)) -> list[ChannelBotOut]:
    result = await session.execute(select(ChannelBot).order_by(ChannelBot.role, ChannelBot.created_at))
    return [ChannelBotOut.from_model(bot) for bot in result.scalars().all()]


@router.post("/extract-style", response_model=ExtractStyleResponse)
async def extract_style_endpoint(
    payload: ExtractStyleRequest, session: AsyncSession = Depends(get_db)
) -> ExtractStyleResponse:
    """StyleExtractor (аудит, п.7.2): по примерам постов LLM предлагает
    persona-промпт. Ничего не сохраняет — оператор вставляет результат в
    персону бота сам."""
    settings = await get_effective_settings(session)
    try:
        suggested = await extract_style(LLMClient(settings), payload.reference_posts)
    except StyleExtractorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExtractStyleResponse(suggested_persona=suggested)


@router.post("", response_model=ChannelBotOut)
async def create_channel_bot(
    payload: ChannelBotCreate, session: AsyncSession = Depends(get_db)
) -> ChannelBotOut:
    bot = ChannelBot(
        theme_id=payload.theme_id,
        role=payload.role,
        bot_token=payload.bot_token,
        persona_prompt=payload.persona_prompt,
        cadence=payload.cadence,
    )
    session.add(bot)
    # Единственность (активный THEME на тему / активный ADMIN) держит партиал-
    # индекс в БД — ловим гонку и повтор на уровне констрейнта, а не проверкой
    # select-ом заранее (та не атомарна).
    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=_uniqueness_message(exc)) from exc
    return ChannelBotOut.from_model(bot)


@router.put("/{channel_bot_id}", response_model=ChannelBotOut)
async def update_channel_bot(
    channel_bot_id: UUID, payload: ChannelBotUpdate, session: AsyncSession = Depends(get_db)
) -> ChannelBotOut:
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")

    if payload.bot_token is not None:
        bot.bot_token = payload.bot_token
        await record_audit(session, AuditAction.BOT_TOKEN_CHANGE, "channel_bot", str(bot.id))
    if payload.persona_prompt is not None:
        bot.persona_prompt = payload.persona_prompt
    if payload.cadence is not None:
        bot.cadence = payload.cadence
    if payload.is_active is not None:
        bot.is_active = payload.is_active
    if "theme_id" in payload.model_fields_set:
        if bot.role == BotRole.ADMIN and payload.theme_id is not None:
            raise HTTPException(status_code=400, detail="role=admin не привязывается к теме")
        if bot.role == BotRole.THEME and payload.theme_id is None:
            raise HTTPException(status_code=400, detail="theme_id обязателен для role=theme")
        bot.theme_id = payload.theme_id

    # Реактивация (is_active=True) или смена темы могут столкнуться с уже
    # активным ботом — тот же партиал-индекс ловит это здесь.
    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=_uniqueness_message(exc)) from exc
    return ChannelBotOut.from_model(bot)


@router.delete("/{channel_bot_id}", status_code=204)
async def delete_channel_bot(
    channel_bot_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    """Полное удаление бота. Процесс ботов подхватит удаление на следующем
    reconcile-тике (hot-reload) и остановит его поллинг без рестарта."""
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")
    await session.delete(bot)
    await session.commit()
