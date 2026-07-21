"""Effective LLM-креды = DB-оверрайд (PanelSettings, задаётся из панели) поверх
.env (Settings) — та же идея, что .env как база + панель как runtime-патч,
без которой пришлось бы пересобирать/перезапускать процесс на каждую смену
ключа. Единственная точка, откуда LLMClient/EmbeddingsClient должны получать
settings в контекстах, где есть AsyncSession (сейчас — scheduler.py); там, где
сессии нет (bootstrap/скрипты), обычный get_settings() по-прежнему верен."""

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.services.panel_settings import get_or_create_panel_settings


async def get_effective_settings(session: AsyncSession) -> Settings:
    base = get_settings()
    panel_settings = await get_or_create_panel_settings(session)

    overrides: dict[str, str] = {}
    if panel_settings.anthropic_api_key_override:
        overrides["anthropic_api_key"] = panel_settings.anthropic_api_key_override
    if panel_settings.voyage_api_key_override:
        overrides["voyage_api_key"] = panel_settings.voyage_api_key_override

    if not overrides:
        return base
    return base.model_copy(update=overrides)
