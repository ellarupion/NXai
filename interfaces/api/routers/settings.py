"""Секрет-оверрайды LLM-ключей (anthropic/voyage) и Telegram-креды пула Telethon
(api_id/api_hash с my.telegram.org) — вводятся в панели вместо .env (см.
core/services/effective_settings.py). Раздел gated require_superadmin целиком:
даже статус ("задан"/"не задан") — это операционная деталь, не нужная
обычному оператору темы."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.services.panel_settings import get_or_create_panel_settings, update_secret_overrides
from interfaces.api.auth import get_current_admin, require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_superadmin)])

# Таймзона — операционная настройка (влияет на тихие часы публикации), не
# секрет, поэтому её GET/PUT доступны любому админу, а не только суперадмину;
# отдельный роутер с более мягкой зависимостью.
general_router = APIRouter(
    prefix="/settings/general", tags=["settings"], dependencies=[Depends(get_current_admin)]
)


class GeneralSettingsOut(BaseModel):
    timezone: str
    pool_cooldown_days: int


class GeneralSettingsUpdate(BaseModel):
    timezone: str | None = None
    pool_cooldown_days: int | None = None


@general_router.get("", response_model=GeneralSettingsOut)
async def get_general_settings(session: AsyncSession = Depends(get_db)) -> GeneralSettingsOut:
    panel_settings = await get_or_create_panel_settings(session)
    return GeneralSettingsOut(
        timezone=panel_settings.timezone, pool_cooldown_days=panel_settings.pool_cooldown_days
    )


@general_router.put("", response_model=GeneralSettingsOut)
async def update_general_settings(
    payload: GeneralSettingsUpdate, session: AsyncSession = Depends(get_db)
) -> GeneralSettingsOut:
    panel_settings = await get_or_create_panel_settings(session)
    if payload.timezone is not None:
        try:
            ZoneInfo(payload.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Неизвестная таймзона «{payload.timezone}» — используйте IANA-имя, например Europe/Moscow",
            ) from exc
        panel_settings.timezone = payload.timezone
    if payload.pool_cooldown_days is not None:
        if payload.pool_cooldown_days < 0:
            raise HTTPException(status_code=400, detail="Кулдаун пула не может быть отрицательным")
        panel_settings.pool_cooldown_days = payload.pool_cooldown_days
    await session.commit()
    return GeneralSettingsOut(
        timezone=panel_settings.timezone, pool_cooldown_days=panel_settings.pool_cooldown_days
    )


class SecretStatus(BaseModel):
    """Никогда не отдаём сырой ключ обратно в ответ — только откуда он сейчас
    эффективно берётся, чтобы форма в панели могла показать "задан из .env" /
    "задан из панели" / "не задан", не раскрывая значение."""

    source: str  # "panel" | "env" | "unset"


class SettingsOut(BaseModel):
    anthropic_api_key: SecretStatus
    voyage_api_key: SecretStatus
    telegram_api_id: SecretStatus
    telegram_api_hash: SecretStatus


class SecretsUpdate(BaseModel):
    """`None` — не менять, `""`/`0` — сбросить оверрайд (вернуться к .env)."""

    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None


def _status(override: str | int, env_value: str | int) -> SecretStatus:
    if override:
        return SecretStatus(source="panel")
    if env_value:
        return SecretStatus(source="env")
    return SecretStatus(source="unset")


@router.get("", response_model=SettingsOut)
async def get_settings_status(session: AsyncSession = Depends(get_db)) -> SettingsOut:
    panel_settings = await get_or_create_panel_settings(session)
    env_settings = get_settings()
    return SettingsOut(
        anthropic_api_key=_status(panel_settings.anthropic_api_key_override, env_settings.anthropic_api_key),
        voyage_api_key=_status(panel_settings.voyage_api_key_override, env_settings.voyage_api_key),
        telegram_api_id=_status(panel_settings.telegram_api_id_override, env_settings.telegram_api_id),
        telegram_api_hash=_status(panel_settings.telegram_api_hash_override, env_settings.telegram_api_hash),
    )


@router.put("", response_model=SettingsOut)
async def update_settings_secrets(
    payload: SecretsUpdate, session: AsyncSession = Depends(get_db)
) -> SettingsOut:
    await update_secret_overrides(
        session,
        anthropic_api_key=payload.anthropic_api_key,
        voyage_api_key=payload.voyage_api_key,
        telegram_api_id=payload.telegram_api_id,
        telegram_api_hash=payload.telegram_api_hash,
    )
    await session.commit()
    return await get_settings_status(session)
