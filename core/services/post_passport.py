"""Паспорт поста: сбор фактов на каждой стадии и одна функция записи.

Стадий четыре, и каждая знает то, чего не знают остальные:

  отбор     — какой был скор, какой порог он проходил, сколько пересылок и какая
              медиана у канала, каким было доверие источнику;
  рерайт    — какой персоной писали, сколько заняло, насколько результат разошёлся
              с исходником по длине, какая подтема и откуда она взялась;
  правка    — что поправил редактор и через что: панель или бот;
  публикация — в какие каналы уехало и с фото ли.

Факты складываются в один словарь по мере прохождения — поэтому merge, а не запись
целиком: стадии идут в разное время и в разных транзакциях, и вторая не должна
затирать первую.

Сборщики фактов вынесены в чистые функции намеренно: их можно проверить тестом без
базы, а именно в них живёт смысл — что считать честным ответом на вопрос «почему такой
пост». Например, у поста, заказанного оператором вручную, порога не было вовсе, и
писать туда действующий порог значило бы соврать: панель нарисовала бы «прошёл порог»,
которого никто не применял.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.post_passport import PostPassport

logger = get_logger(__name__)


async def merge_passport(session: AsyncSession, candidate_id: UUID, facts: dict) -> None:
    """Дописывает факты к паспорту кандидата, не затирая уже записанные стадии.

    Не роняет вызывающую операцию: паспорт — справка для человека, и потерять из-за
    неё готовый пост было бы абсурдом."""
    if not facts:
        return
    try:
        row = (
            await session.execute(
                select(PostPassport).where(PostPassport.candidate_post_id == candidate_id)
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(PostPassport(candidate_post_id=candidate_id, data=dict(facts)))
        else:
            # Присваиваем НОВЫЙ словарь, а не правим на месте: SQLAlchemy не отследит
            # мутацию внутри JSONB, и правка тихо не сохранится.
            row.data = {**(row.data or {}), **facts}
        await session.flush()
    except Exception:
        logger.exception("passport.merge_failed", candidate_id=str(candidate_id))


# --- сборщики фактов (чистые) ----------------------------------------------


def selection_facts(
    *,
    origin: str,
    score: float | None,
    threshold: float | None,
    forwards: int | None = None,
    median_forwards: float | None = None,
    trust_score: float | None = None,
) -> dict:
    """origin: 'auto' — отобран порогом, 'manual' — заказан кнопкой, 'batch' — партией
    на день. У ручных порога НЕ было: threshold=None, и панель скажет об этом словами
    вместо того, чтобы рисовать несуществующее сравнение."""
    return {
        "origin": origin,
        "score": round(score, 3) if score is not None else None,
        "threshold": round(threshold, 3) if threshold is not None else None,
        "forwards": forwards,
        "median_forwards": round(median_forwards, 2) if median_forwards is not None else None,
        "trust_score": round(trust_score, 3) if trust_score is not None else None,
    }


def rewrite_facts(
    *,
    model: str,
    persona_summary: str,
    source_length: int,
    result_length: int,
    variant_no: int,
    source_similarity: float | None = None,
) -> dict:
    return {
        "model": model,
        "persona": persona_summary or "персона не задана",
        "source_length": source_length,
        "result_length": result_length,
        "variant_no": variant_no,
        "source_similarity": (
            round(source_similarity, 3) if source_similarity is not None else None
        ),
    }


def rubric_facts(*, rubric: str | None, decided_by: str) -> dict:
    """decided_by: 'raw' — подтему определили по исходнику ещё при отборе (так делает
    партия на день, чтобы разложить пул по подтемам ДО оплаты рерайта), 'rewritten' —
    по готовому тексту. Разница важна: во втором случае классификатор видел то же, что
    увидит читатель."""
    return {"rubric": rubric, "rubric_decided_by": decided_by}


def edit_facts(*, via: str, length_before: int, length_after: int) -> dict:
    return {"edited_via": via, "edit_length_before": length_before, "edit_length_after": length_after}


def publish_facts(*, channels: list[str], with_photo: bool) -> dict:
    return {"published_to": channels, "published_with_photo": with_photo}


def persona_summary(persona_prompt: str) -> str:
    """Короткая выжимка персоны для паспорта: целиком промпт может быть на страницу,
    и в справке он бесполезен — важно, чем именно писали, а не весь текст."""
    text = " ".join((persona_prompt or "").split())
    return text[:200] + ("…" if len(text) > 200 else "")
