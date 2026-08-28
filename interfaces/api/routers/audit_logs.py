"""Чтение журнала действий.

Журнал писался с самого начала, но прочитать его было нечем: эндпоинта не
существовало, и таблица просто росла. На вопрос «кто одобрил этот пост» или «когда
меняли ключ» отвечать приходилось запросом в базу руками.

Только суперадмину: журнал показывает входы в панель и смену ключей — ровно то, что в
панели уже закрыто той же ролью.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.audit_log import AuditLog
from core.models.enums import AuditAction
from core.models.theme import Theme
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/audit-logs", tags=["audit-logs"], dependencies=[Depends(require_superadmin)]
)

MAX_LIMIT = 200


class AuditLogOut(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    entity_type: str
    entity_id: str
    # Кто действовал. Оба пустые — действие системное: планировщик, приём постов,
    # автоматическое перекрытие рекламы.
    actor_admin_username: str | None
    actor_tg_user_id: int | None
    actor_ip: str | None
    theme_id: UUID | None
    theme_name: str | None
    payload: dict


class AuditLogsOut(BaseModel):
    items: list[AuditLogOut]
    # Есть ли что грузить дальше — чтобы кнопка «Показать ещё» появлялась только
    # когда это осмысленно.
    has_more: bool


@router.get("", response_model=AuditLogsOut)
async def list_audit_logs(
    action: AuditAction | None = None,
    theme_id: UUID | None = None,
    actor: str | None = None,
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> AuditLogsOut:
    stmt = (
        select(AuditLog, Theme.name)
        # Внешнее соединение: тему могли удалить, а запись журнала обязана пережить
        # удаление — иначе история действий исчезала бы вместе с темой.
        .outerjoin(Theme, Theme.id == AuditLog.theme_id)
        .order_by(AuditLog.created_at.desc())
    )
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if theme_id is not None:
        stmt = stmt.where(AuditLog.theme_id == theme_id)
    if actor:
        stmt = stmt.where(func.lower(AuditLog.actor_admin_username).contains(actor.lower()))

    # limit+1, чтобы отличить «ровно столько» от «есть ещё» без второго запроса.
    rows = (await session.execute(stmt.offset(offset).limit(limit + 1))).all()
    has_more = len(rows) > limit

    return AuditLogsOut(
        items=[
            AuditLogOut(
                id=log.id,
                created_at=log.created_at,
                action=log.action.value,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                actor_admin_username=log.actor_admin_username,
                actor_tg_user_id=log.actor_tg_user_id,
                actor_ip=log.actor_ip,
                theme_id=log.theme_id,
                theme_name=theme_name,
                payload=log.payload or {},
            )
            for log, theme_name in rows[:limit]
        ],
        has_more=has_more,
    )
