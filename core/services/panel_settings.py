"""Доступ к singleton-строке PanelSettings (first-row-or-create — та же
первая-строка-таблицы модель, что admin/audit_log в NX). Секрет-оверрайды
(anthropic/voyage) читаются отсюда effective_settings.py, а не напрямую —
роутер панели никогда не должен обращаться к таблице в обход этого сервиса."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.panel_settings import PanelSettings


async def get_or_create_panel_settings(session: AsyncSession) -> PanelSettings:
    result = await session.execute(select(PanelSettings).limit(1))
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        settings_row = PanelSettings()
        session.add(settings_row)
        await session.flush()
    return settings_row


async def update_secret_overrides(
    session: AsyncSession,
    *,
    anthropic_api_key: str | None = None,
    voyage_api_key: str | None = None,
) -> PanelSettings:
    """`None` — оставить как есть, `""` — сбросить оверрайд (вернуться к
    .env-значению), непустая строка — новый оверрайд. Отличать "не трогать"
    от "сбросить" важно: иначе не было бы способа откатиться на .env-ключ
    из панели, если DB-оверрайд оказался невалидным."""
    settings_row = await get_or_create_panel_settings(session)
    if anthropic_api_key is not None:
        settings_row.anthropic_api_key_override = anthropic_api_key
    if voyage_api_key is not None:
        settings_row.voyage_api_key_override = voyage_api_key
    await session.flush()
    return settings_row
