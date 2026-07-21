"""Отметки живости фоновых процессов (core/models/worker_heartbeat.py).

Каждый воркер зовёт record_heartbeat на своём тике/цикле; панель через
list_stale_workers видит, кто замолчал. Отдельная короткая транзакция —
heartbeat не должен зависеть от успеха основной работы тика (иначе как раз
в момент сбоя, когда сигнал важнее всего, он бы и не записался)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session_factory
from core.logging import get_logger
from core.models.worker_heartbeat import WorkerHeartbeat

logger = get_logger(__name__)

# Имена процессов — держим списком, чтобы панель показывала «нет ни одного
# удара» даже для процесса, который ещё ни разу не поднимался.
WORKER_SCHEDULER = "scheduler"
WORKER_INGEST = "ingest"
WORKER_BOTS = "bots"
KNOWN_WORKERS = (WORKER_SCHEDULER, WORKER_INGEST, WORKER_BOTS)

# Порог «замолчал» для каждого процесса. scheduler бьётся ~раз в минуту,
# ingest/bots — реже (они на long-polling, отдельный тик им ни к чему), но
# бьются по таймеру. Держим единый щедрый порог, чтобы не ловить ложные
# срабатывания на редких паузах.
STALE_AFTER = timedelta(minutes=10)


async def record_heartbeat(worker_name: str, detail: str | None = None) -> None:
    """Upsert строки по имени процесса в собственной короткой транзакции."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        heartbeat = await session.get(WorkerHeartbeat, worker_name)
        now = datetime.now(timezone.utc)
        if heartbeat is None:
            session.add(WorkerHeartbeat(worker_name=worker_name, last_beat_at=now, detail=detail))
        else:
            heartbeat.last_beat_at = now
            heartbeat.detail = detail
        await session.commit()


async def list_worker_status(session: AsyncSession, now: datetime | None = None) -> list[dict]:
    """Статус всех известных процессов для панели: имя, когда бился в последний
    раз, живой ли (по STALE_AFTER), детально. Процесс, который ещё ни разу не
    поднимался, попадает сюда как never/stale."""
    now = now or datetime.now(timezone.utc)
    result = await session.execute(select(WorkerHeartbeat))
    by_name = {row.worker_name: row for row in result.scalars().all()}

    statuses: list[dict] = []
    for name in KNOWN_WORKERS:
        row = by_name.get(name)
        if row is None:
            statuses.append({"worker_name": name, "last_beat_at": None, "is_alive": False, "detail": None})
            continue
        is_alive = now - row.last_beat_at <= STALE_AFTER
        statuses.append(
            {
                "worker_name": name,
                "last_beat_at": row.last_beat_at,
                "is_alive": is_alive,
                "detail": row.detail,
            }
        )
    return statuses
