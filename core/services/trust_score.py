"""Корректировка SourceChannel.trust_score по исходам его кандидатов —
источник, чьи посты систематически не проходят скоринг/дедуп, постепенно
теряет вес при последующем скоринге (core/services/scoring.py:record_snapshot
умножает итоговый score на trust_score), вместо того чтобы решение о доверии
принималось только вручную в панели (ROADMAP.md Phase 5 изначально это
планировало как ручной вывод источника из ротации — здесь это происходит
постепенно и автоматически, панель лишь показывает текущее значение)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.source_channel import SourceChannel

MIN_TRUST_SCORE = 0.1
MAX_TRUST_SCORE = 2.0

# Дубликат — источник просто повторил чужую новость (мягкий сигнал), явный
# reject (ручной или по таймауту дозревания) — источник дал заведомо слабый
# пост, штраф больше. Успешный рерайт — источник исправно поставляет контент.
REJECTED_PENALTY = 0.05
DUPLICATE_PENALTY = 0.02
SUCCESS_BONUS = 0.02


async def adjust_trust_score(session: AsyncSession, source_channel_id: UUID, delta: float) -> None:
    source_channel = await session.get(SourceChannel, source_channel_id)
    if source_channel is None:
        return
    source_channel.trust_score = max(
        MIN_TRUST_SCORE, min(MAX_TRUST_SCORE, source_channel.trust_score + delta)
    )
    await session.flush()
