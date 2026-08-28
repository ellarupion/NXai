"""Подтемы внутри темы: подбор списка, классификация постов, баланс выдачи.

Зачем. Тема — это ниша целиком («мужской канал»), но контент внутри неё
разный: деньги, отношения, здоровье, карьера. Без деления канал легко выдаёт
день из пяти постов про одно и то же — и это не случайность, а следствие
устройства: источники в один день пишут об одном (инфоповод общий), а скоринг
это усиливает, потому что виральное в нише оказывается виральным сразу у всех.
Читатель видит перекос как «канал зациклился».

Три части, каждая решает свой кусок:

  * suggest_rubrics — ИИ предлагает разбиение под конкретную нишу. Список
    остаётся за оператором: он правится руками и хранится в Theme.rubrics.
  * classify — относит готовый рерайт к одной из рубрик темы. Дешёвой моделью
    и по УЖЕ переписанному тексту, а не по исходнику: публиковать будем
    именно его, и рубрика должна описывать то, что выйдет.
  * pick_balanced — выбирает, какой пост ставить следующим, учитывая, что
    выходило до него.
"""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import CLASSIFICATION_MODEL, LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus, LlmUsageKind
from core.models.source_channel import SourceChannel
from core.models.theme import Theme
from core.services.llm_usage import record_usage

logger = get_logger(__name__)

MAX_RUBRICS = 8
# Сколько последних публикаций смотрим, решая, не приелась ли рубрика.
RECENT_WINDOW = 4


class RubricError(Exception):
    """Текст уходит в панель как есть."""


async def suggest_rubrics(session: AsyncSession, theme_id: UUID) -> list[str]:
    """ИИ предлагает разбиение ниши на подтемы.

    Просим не абстрактную таксономию, а деление, по которому реально
    распадается контент ниши: рубрики должны быть примерно сопоставимы по
    объёму, иначе одна соберёт 80% постов и чередовать будет нечего."""
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise RubricError("Тема не найдена")

    sources = (
        await session.execute(
            select(SourceChannel.title).where(SourceChannel.theme_id == theme_id).limit(15)
        )
    ).scalars().all()

    context = [f"Ниша канала: {theme.name}"]
    if theme.default_style_prompt:
        context.append(f"Стиль: {theme.default_style_prompt[:300]}")
    if sources:
        context.append("Каналы-источники: " + ", ".join(sources))

    system = (
        "Ты делишь нишу Telegram-канала на подтемы (рубрики) для чередования "
        "публикаций.\n\n"
        "Правила: от 4 до 6 рубрик; каждая 1-2 слова, существительное; "
        "рубрики не пересекаются и вместе покрывают нишу; примерно сопоставимы "
        "по объёму контента — если одна соберёт большинство постов, чередовать "
        "будет нечего; без слов «прочее», «разное», «другое».\n"
        "Ответ — ТОЛЬКО JSON-массив строк, без markdown."
    )

    from core.services.effective_settings import get_effective_settings

    try:
        result = await LLMClient(await get_effective_settings(session)).complete(
            model=CLASSIFICATION_MODEL,
            system_prompt=system,
            user_prompt="\n".join(context),
            cache_system_prompt=False,
            max_tokens=300,
        )
        await record_usage(
            session, result, kind=LlmUsageKind.SUGGEST_RUBRICS,
            model=CLASSIFICATION_MODEL, theme_id=theme_id,
        )
    except Exception as exc:
        logger.warning("rubrics.suggest_failed", error=type(exc).__name__)
        raise RubricError(
            "ИИ не ответил — проверьте ключ Anthropic в «Настройках». "
            "Рубрики можно задать и вручную"
        ) from exc

    rubrics = _parse_list(result.text)
    if not rubrics:
        raise RubricError("Не удалось подобрать рубрики — задайте их вручную")
    return rubrics[:MAX_RUBRICS]


def _parse_list(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        return [
            line.strip(" -–—•\"'")
            for line in raw.splitlines()
            if 1 < len(line.strip()) < 40
        ][:MAX_RUBRICS]
    if not isinstance(parsed, list):
        return []
    return [str(x).strip() for x in parsed if str(x).strip()]


async def classify(
    session: AsyncSession, theme_id: UUID, text: str, llm: LLMClient | None = None
) -> str | None:
    """Относит текст к одной из рубрик темы. None — рубрики не заданы или
    классификация не удалась.

    Сбой классификации намеренно НЕ считается ошибкой поста: рубрика — это
    удобство раскладки, а не условие публикации. Пост без рубрики выйдет,
    просто не будет участвовать в чередовании."""
    theme = await session.get(Theme, theme_id)
    if theme is None or not theme.rubrics:
        return None

    rubrics = list(theme.rubrics)
    system = (
        "Отнеси пост ровно к одной рубрике из списка. Ответ — ТОЛЬКО название "
        "рубрики, слово в слово из списка, без пояснений и знаков.\n\n"
        "Рубрики: " + "; ".join(rubrics)
    )
    try:
        if llm is None:
            from core.services.effective_settings import get_effective_settings

            llm = LLMClient(await get_effective_settings(session))
        result = await llm.complete(
            model=CLASSIFICATION_MODEL,
            system_prompt=system,
            user_prompt=text[:2000],
            cache_system_prompt=False,
            max_tokens=30,
        )
        # Классификация дешёвая, но частая: на партию в 8 постов приходится до
        # 32 вызовов на пуле отбора. Без учёта эта строка расходов была бы невидимой
        # именно потому, что каждый вызов копеечный.
        await record_usage(
            session, result, kind=LlmUsageKind.CLASSIFY_RUBRIC,
            model=CLASSIFICATION_MODEL, theme_id=theme_id,
        )
    except Exception as exc:
        logger.warning("rubrics.classify_failed", error=type(exc).__name__)
        return None

    answer = result.text.strip().strip('".«»').lower()
    for rubric in rubrics:
        if rubric.lower() == answer:
            return rubric
    # Модель могла ответить близко, но не дословно — принимаем вхождение,
    # чтобы не терять классификацию из-за лишнего слова.
    for rubric in rubrics:
        if rubric.lower() in answer or answer in rubric.lower():
            return rubric
    logger.info("rubrics.classify_no_match", answer=answer[:60])
    return None


async def recent_rubrics(session: AsyncSession, theme_id: UUID, limit: int = RECENT_WINDOW) -> list[str]:
    """Рубрики последних опубликованных постов темы, свежие первыми."""
    rows = (
        await session.execute(
            select(CandidatePost.rubric)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                SourceChannel.theme_id == theme_id,
                CandidatePost.rubric.is_not(None),
                CandidatePost.status == CandidatePostStatus.PUBLISHED,
            )
            .order_by(CandidatePost.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [r for r in rows if r]


def freshest_by_rubric(candidates: list, recent: list[str]) -> list:
    """Сужает список готовых постов до тех, чья рубрика дольше всех не выходила.

    Возвращает ПОДМНОЖЕСТВО, а не один пост, и это принципиально: выбор внутри
    темы взвешенно-случайный по скору (core/services/scheduler_pool.py), чтобы
    порядок выхода не был предсказуемым. Верни мы отсюда конкретный пост —
    рубрики бы выровнялись, но канал начал бы крутить строго лучший по скору
    пост каждой рубрики по кругу. Поэтому здесь только отсев, а бросок кубика
    остаётся за вызывающим.

    Не жёсткий запрет, а предпочтение: если все готовые посты одной рубрики,
    вернётся весь список — выйдет пост этой рубрики, а не тишина. Пустая
    очередь хуже перекоса.

    Посты без рубрики считаются максимально «давними» — иначе тема, где
    рубрики только что включили, встала бы: накопленное неклассифицированное
    никогда не догнало бы свежее размеченное."""
    if not candidates or not recent:
        return list(candidates)

    def staleness(candidate) -> int:
        rubric = getattr(candidate, "rubric", None)
        if rubric is None:
            return len(recent) + 1
        try:
            # Индекс в списке недавних: 0 — вышла последней, то есть самая
            # свежая и наименее желанная сейчас.
            return recent.index(rubric)
        except ValueError:
            return len(recent) + 1

    best = max(staleness(c) for c in candidates)
    return [c for c in candidates if staleness(c) == best]
