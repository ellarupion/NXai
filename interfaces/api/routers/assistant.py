"""Вопрос помощнику.

Один эндпоинт и никакого состояния на сервере: переписку держит панель и присылает
целиком (см. заголовок core/services/assistant.py). Заводить таблицу с историей ради
разговора, который живёт минуты, незачем.

История приходит от клиента, то есть снаружи. Подделать в ней «реплику помощника»
может только уже вошедший админ, и ничего сверх своих прав он этим не получит:
инструменты помощника — только на чтение, а всё, что он мог бы прочитать, тот же
админ и так видит в панели. Служебные роли из присланной истории всё равно
выбрасываются (_clean_history) — чтобы в переписку нельзя было подложить якобы
системное правило.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.assistant import AssistantService
from core.services.llm_budget import DailyBudgetExceededError
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/assistant", tags=["assistant"], dependencies=[Depends(get_current_admin)]
)

# Потолок на присланную историю. В модель уходит только хвост (HISTORY_MAX_MESSAGES),
# но принимать мегабайт, чтобы тут же его выбросить, незачем.
MAX_HISTORY = 100


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)


class AskResponse(BaseModel):
    answer: str
    # Что помощник смотрел — панель показывает это под ответом, чтобы ответ можно было
    # отличить от придуманного.
    used: list[str]
    cost_usd: float


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, session: AsyncSession = Depends(get_db)) -> AskResponse:
    try:
        answer = await AssistantService(session).ask(
            [turn.model_dump() for turn in payload.history], payload.question
        )
    except DailyBudgetExceededError as exc:
        # 402, как у остальных дорогих операций: панель по коду понимает, что дело в
        # потолке расходов, и говорит об этом словами, а не показывает красную ошибку.
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AskResponse(
        answer=answer.text, used=answer.used, cost_usd=round(answer.cost_usd, 6)
    )
