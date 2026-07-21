"""CRUD ботов (тематических и admin) — токены живут в БД (core/models/channel_bot.py),
не в .env, поэтому ввод/смена токена — операция панели, а не SSH. gated
require_superadmin целиком: bot_token — секрет уровня прод-инцидента при утечке."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.channel_bot import DEFAULT_CADENCE, ChannelBot
from core.models.enums import BotRole
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/channel-bots", tags=["channel-bots"], dependencies=[Depends(require_superadmin)])


class ChannelBotOut(BaseModel):
    id: UUID
    theme_id: UUID | None
    role: BotRole
    persona_prompt: str
    cadence: dict
    is_active: bool
    token_set: bool

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


@router.get("", response_model=list[ChannelBotOut])
async def list_channel_bots(session: AsyncSession = Depends(get_db)) -> list[ChannelBotOut]:
    result = await session.execute(select(ChannelBot).order_by(ChannelBot.role, ChannelBot.created_at))
    return [ChannelBotOut.from_model(bot) for bot in result.scalars().all()]


@router.post("", response_model=ChannelBotOut)
async def create_channel_bot(
    payload: ChannelBotCreate, session: AsyncSession = Depends(get_db)
) -> ChannelBotOut:
    if payload.role == BotRole.ADMIN:
        existing = await session.execute(select(ChannelBot).where(ChannelBot.role == BotRole.ADMIN))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400, detail="Admin-бот уже создан — отредактируйте существующую запись"
            )

    bot = ChannelBot(
        theme_id=payload.theme_id,
        role=payload.role,
        bot_token=payload.bot_token,
        persona_prompt=payload.persona_prompt,
        cadence=payload.cadence,
    )
    session.add(bot)
    await session.flush()
    await session.commit()
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

    await session.flush()
    await session.commit()
    return ChannelBotOut.from_model(bot)
