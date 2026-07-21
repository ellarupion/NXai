from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class WorkerHeartbeat(Base, TimestampMixin):
    """Отметка «живости» фонового процесса. Каждый воркер (scheduler, ingest,
    bots) обновляет свою строку на каждом тике/цикле — панель по разнице между
    last_beat_at и now понимает, что процесс упал или завис, чего не видят
    остальные алерты (они проверяют конфигурацию и данные, а не то, крутятся
    ли сами процессы — аудит, п.3.1).

    worker_name — PK: строк ровно столько, сколько типов процессов, upsert по
    имени. Отдельная сессия-читалка (метрики целевых каналов, Phase 5) при
    появлении получит своё имя."""

    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Свободный статус-текст для диагностики («12 каналов», «flood_wait 300с») —
    # не обязателен, панель показывает его как есть, если задан.
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
