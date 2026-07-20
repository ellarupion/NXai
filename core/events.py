"""Публикация событий ядра в Redis pub/sub.

В отличие от NX (где это была точка расширения "на будущее"), здесь шина —
рабочая часть пайплайна: ingest публикует "новый кандидат", scorer/dedup/
rewriter подписываются и обрабатывают асинхронно, вместо того чтобы всё
происходило синхронно в одном воркере. Формат сообщения: {"type", "payload"}.
"""

import json
from typing import Any

import redis.asyncio as redis

from core.config import Settings, get_settings

CHANNEL = "core:events"

# Типы событий пайплайна (см. ARCHITECTURE.md §2).
CANDIDATE_INGESTED = "candidate.ingested"
CANDIDATE_SCORED = "candidate.scored"
CANDIDATE_SELECTED = "candidate.selected"
CANDIDATE_REWRITTEN = "candidate.rewritten"
POST_PUBLISHED = "post.published"
FOREIGN_POST_DETECTED = "foreign_post.detected"
FOREIGN_POST_COVERED = "foreign_post.covered"


class EventBus:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "payload": payload})
        await self._redis.publish(CHANNEL, message)

    async def close(self) -> None:
        await self._redis.aclose()


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
