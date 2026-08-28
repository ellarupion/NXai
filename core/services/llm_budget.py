"""Дневной потолок расходов на ИИ.

Ничто не мешало за день случайно потратить месячный бюджет: ни ограничения, ни
предупреждения. Здесь и то, и другое.

Два правила, из которых всё следует:

1. **Молча ничего не выключается.** Упёрлись в потолок — операция отказывается с
   человеческим текстом, который виден в панели и в карточке у редактора. Лимит
   настраивается там же, где остальное поведение, и по умолчанию выключен: включать
   ограничение, способное остановить работу, — решение владельца, а не наше.

2. **Останавливаем только дорогое и только необязательное.** Под лимит попадает то,
   что владелец запускает сам и может повторить завтра: партия постов на день, подбор
   подтем, поиск источников, проба персоны. Приём постов от источников, скоринг и сама
   публикация к модели не обращаются вовсе, так что канал не встанет и уже готовые
   посты выйдут по расписанию.

Про автоматический рерайт в планировщике решение отдельное: он тоже дорогой, и его
лимит останавливает. Иначе потолок не защищал бы ровно от того случая, ради которого
заведён, — фонового расхода, который никто не запускал руками.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.services.automation import get_automation
from core.services.llm_usage import spent_today_usd

logger = get_logger(__name__)


class DailyBudgetExceededError(Exception):
    """Дневной потолок исчерпан — до полуночи дорогие операции не работают.

    Наследуемся от Exception, а не от ValueError: роутеры ловят её отдельно и
    показывают текст как есть, не подмешивая к ошибкам проверки полей."""


@dataclass(frozen=True)
class BudgetState:
    limit_usd: float
    spent_usd: float

    @property
    def enabled(self) -> bool:
        return self.limit_usd > 0

    @property
    def exceeded(self) -> bool:
        return self.enabled and self.spent_usd >= self.limit_usd

    @property
    def percent(self) -> int:
        if not self.enabled:
            return 0
        return min(999, int(round(self.spent_usd / self.limit_usd * 100)))

    def near_limit(self, warn_percent: int) -> bool:
        return self.enabled and not self.exceeded and self.percent >= warn_percent


async def get_budget_state(session: AsyncSession) -> BudgetState:
    automation = await get_automation(session)
    return BudgetState(
        limit_usd=automation.daily_budget_usd,
        spent_usd=await spent_today_usd(session),
    )


async def ensure_budget(session: AsyncSession) -> None:
    """Бросает DailyBudgetExceededError, если дневной потолок исчерпан.

    Вызывается ПЕРЕД дорогой операцией. Проверка «до», а не «после»: узнать о переборе
    постфактум бессмысленно — деньги уже потрачены."""
    state = await get_budget_state(session)
    if not state.exceeded:
        return
    logger.warning(
        "llm_budget.exceeded", limit_usd=state.limit_usd, spent_usd=round(state.spent_usd, 4)
    )
    raise DailyBudgetExceededError(
        f"Дневной лимит расходов на ИИ исчерпан: потрачено ${state.spent_usd:.2f} "
        f"из ${state.limit_usd:.2f}. Лимит обнулится в полночь, а поднять или снять его "
        f"можно в «Настройках», раздел «Расходы на ИИ»."
    )
