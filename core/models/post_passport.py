import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PostPassport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Паспорт поста — из чего он получился.

    Система принимает на каждый пост несколько решений: взять этот, а не соседний;
    какой был скор и какой порог он проходил; какой персоной переписывали; к какой
    подтеме отнесли и почему; что поправил редактор; в какие каналы уехало. До
    паспорта ни одно из них не сохранялось — всё уходило в логи, а человеку
    доставалась карточка с текстом и числом виральности.

    Отсюда и разборы вида «почему вышел именно такой пост»: чтобы ответить, приходилось
    выводить это от противного по коду и по времени в логах.

    Одно поле JSONB, а не колонки: набор фактов будет меняться с каждой правкой
    конвейера, и заводить миграцию под каждый — работа без смысла (тот же приём, что у
    PanelSettings.automation). Отдельная таблица, а не колонка в candidate_posts:
    кандидаты читаются на каждой странице очереди сотнями, и лишний JSONB там ни к чему,
    а паспорт открывают по одному и по требованию.

    Цену поста здесь НЕ храним: расход уже подписан идентификатором кандидата в
    llm_usage, и второе место для того же числа рано или поздно разъедется с первым.
    """

    __tablename__ = "post_passports"

    candidate_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_posts.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
