"""CRUD целевых каналов темы — панель может добавить канал только если
тематический бот (ChannelBot role=THEME) уже реально админ там (проверка
через живой Bot API, core/services/target_channels.py), иначе ни публикация,
ни ad watchdog всё равно бы не заработали."""

from uuid import UUID

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole
from core.models.target_channel import TargetChannel
from core.services.target_channels import BotNotAdminError, TargetChannelService
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/target-channels", tags=["target-channels"], dependencies=[Depends(get_current_admin)]
)


class TargetChannelOut(BaseModel):
    id: UUID
    theme_id: UUID
    tg_chat_id: int
    title: str
    signature: str
    is_active: bool
    metrics_session_id: UUID | None
    crosspost: dict

    model_config = {"from_attributes": True}


class TargetChannelCreate(BaseModel):
    theme_id: UUID
    chat_id_or_username: str
    signature: str = ""


class TargetChannelUpdate(BaseModel):
    signature: str | None = None
    is_active: bool | None = None


class SetMetricsSessionPayload(BaseModel):
    metrics_session_id: UUID | None


class SetCrosspostPayload(BaseModel):
    # Свободный JSON: {"vk": {"enabled", "access_token", "owner_id"},
    #                  "max": {"enabled", "access_token", "chat_id"}}
    crosspost: dict


async def _bot_for_theme(session: AsyncSession, theme_id: UUID) -> Bot:
    result = await session.execute(
        select(ChannelBot).where(ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME)
    )
    channel_bot = result.scalar_one_or_none()
    if channel_bot is None:
        raise HTTPException(
            status_code=400, detail="У темы ещё нет бота — сначала создайте его во вкладке «Боты»"
        )
    return Bot(token=channel_bot.bot_token)


@router.get("", response_model=list[TargetChannelOut])
async def list_target_channels(
    theme_id: UUID | None = None, session: AsyncSession = Depends(get_db)
) -> list[TargetChannel]:
    stmt = select(TargetChannel).order_by(TargetChannel.title)
    if theme_id is not None:
        stmt = stmt.where(TargetChannel.theme_id == theme_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TargetChannelOut)
async def create_target_channel(
    payload: TargetChannelCreate, session: AsyncSession = Depends(get_db)
) -> TargetChannel:
    async with await _bot_for_theme(session, payload.theme_id) as bot:
        try:
            target_channel = await TargetChannelService(session).add_target_channel(
                bot, payload.theme_id, payload.chat_id_or_username, payload.signature
            )
        except BotNotAdminError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return target_channel


@router.put("/{target_channel_id}", response_model=TargetChannelOut)
async def update_target_channel(
    target_channel_id: UUID, payload: TargetChannelUpdate, session: AsyncSession = Depends(get_db)
) -> TargetChannel:
    target_channel = await session.get(TargetChannel, target_channel_id)
    if target_channel is None:
        raise HTTPException(status_code=404, detail="TargetChannel not found")
    if payload.signature is not None:
        target_channel.signature = payload.signature
    if payload.is_active is not None:
        target_channel.is_active = payload.is_active
    await session.flush()
    await session.commit()
    return target_channel


@router.put("/{target_channel_id}/metrics-session", response_model=TargetChannelOut)
async def set_metrics_session(
    target_channel_id: UUID,
    payload: SetMetricsSessionPayload,
    session: AsyncSession = Depends(get_db),
) -> TargetChannel:
    """Назначает Telethon-сессию, читающую метрики этого канала (аудит, п.6.2).
    Аккаунт этой сессии должен быть участником канала, иначе Telethon не отдаст
    статистику; None — перестать собирать метрики."""
    target_channel = await session.get(TargetChannel, target_channel_id)
    if target_channel is None:
        raise HTTPException(status_code=404, detail="TargetChannel not found")
    target_channel.metrics_session_id = payload.metrics_session_id
    await session.flush()
    await session.commit()
    return target_channel


@router.put("/{target_channel_id}/crosspost", response_model=TargetChannelOut)
async def set_crosspost(
    target_channel_id: UUID, payload: SetCrosspostPayload, session: AsyncSession = Depends(get_db)
) -> TargetChannel:
    """Настройка кросспоста в VK/MAX (аудит, п.8.4). Токены хранятся в JSONB
    канала; включение — флаг enabled в конфиге платформы."""
    target_channel = await session.get(TargetChannel, target_channel_id)
    if target_channel is None:
        raise HTTPException(status_code=404, detail="TargetChannel not found")
    target_channel.crosspost = payload.crosspost
    await session.flush()
    await session.commit()
    return target_channel
