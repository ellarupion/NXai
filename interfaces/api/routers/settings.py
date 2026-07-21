"""Секрет-оверрайды LLM-ключей (anthropic/voyage) — вводятся в панели вместо
.env (см. core/services/effective_settings.py). Раздел gated require_superadmin
целиком: даже статус ("задан"/"не задан") — это операционная деталь, не
нужная обычному оператору темы."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.services.panel_settings import get_or_create_panel_settings, update_secret_overrides
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_superadmin)])


class SecretStatus(BaseModel):
    """Никогда не отдаём сырой ключ обратно в ответ — только откуда он сейчас
    эффективно берётся, чтобы форма в панели могла показать "задан из .env" /
    "задан из панели" / "не задан", не раскрывая значение."""

    source: str  # "panel" | "env" | "unset"


class SettingsOut(BaseModel):
    anthropic_api_key: SecretStatus
    voyage_api_key: SecretStatus


class SecretsUpdate(BaseModel):
    """`None` — не менять, `""` — сбросить оверрайд (вернуться к .env)."""

    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None


def _status(override: str, env_value: str) -> SecretStatus:
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
    )


@router.put("", response_model=SettingsOut)
async def update_settings_secrets(
    payload: SecretsUpdate, session: AsyncSession = Depends(get_db)
) -> SettingsOut:
    await update_secret_overrides(
        session, anthropic_api_key=payload.anthropic_api_key, voyage_api_key=payload.voyage_api_key
    )
    await session.commit()
    return await get_settings_status(session)
