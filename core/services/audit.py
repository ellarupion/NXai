"""Запись действий в неизменяемый журнал (core/models/audit_log.py).

Что и зачем пишем. Не весь конвейер: приём постов и шаги обработки видны по статусу
кандидата, а выход поста — на странице «Публикации». В журнал идёт то, чего больше
нигде не увидеть, — решения человека и смена доступов: вход, одобрение и отклонение
постов, правка текста, массовая очистка очереди, смена ключей и токенов.

Автор фиксируется явно, а адрес — нет. Логин оператора известен вызывающему (он и так
достаёт его из токена), а вот адрес — свойство соединения: протаскивать его через
record_audit из десятка роутеров значило бы ни разу не забыть, а забыть легко, и тогда
часть записей молча осталась бы без адреса. Поэтому адрес берётся из contextvar, куда
его кладёт middleware API (core/request_context.py).

Не роняет вызывающую операцию, если запись не удалась: журнал — побочный эффект, и
потерять из-за него одобренный пост было бы абсурдом.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.audit_log import AuditLog
from core.models.enums import AuditAction
from core.request_context import current_actor_ip

logger = get_logger(__name__)


async def record_audit(
    session: AsyncSession,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    payload: dict | None = None,
    *,
    actor_admin_username: str | None = None,
    actor_tg_user_id: int | None = None,
    theme_id: UUID | None = None,
) -> None:
    """Оба поля автора пустые = действие системное: планировщик, приём постов,
    автоматическое перекрытие рекламы. Это честнее выдуманного имени."""
    try:
        session.add(
            AuditLog(
                actor_tg_user_id=actor_tg_user_id,
                actor_admin_username=actor_admin_username,
                actor_ip=current_actor_ip(),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                theme_id=theme_id,
                payload=payload or {},
            )
        )
        await session.flush()
    except Exception:
        logger.exception("audit.record_failed", action=action.value)


def _entity_id(value: UUID | str | None) -> str:
    return str(value) if value is not None else ""
