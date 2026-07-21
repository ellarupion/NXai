"""Запись ключевых действий панели в неизменяемый журнал
(core/models/audit_log.py — аудит, п.8.2). Раньше модель существовала, но в
неё никто не писал. Пишем: вход, одобрение/отклонение постов, смену секретов
(ключи, токены ботов). actor_tg_user_id=None означает системное действие;
для операторов панели кладём его пустым (у нас логин/пароль, а не tg-user),
а actor фиксируем в payload по username, чтобы не заводить отдельную колонку.

Не роняет вызывающую операцию, если запись в журнал вдруг не удалась —
аудит это побочный эффект, а не часть бизнес-транзакции."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.audit_log import AuditLog
from core.models.enums import AuditAction

logger = get_logger(__name__)


async def record_audit(
    session: AsyncSession,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
) -> None:
    try:
        session.add(
            AuditLog(
                actor_tg_user_id=None,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload or {},
            )
        )
        await session.flush()
    except Exception:
        logger.exception("audit.record_failed", action=action.value)


def _entity_id(value: UUID | str | None) -> str:
    return str(value) if value is not None else ""
