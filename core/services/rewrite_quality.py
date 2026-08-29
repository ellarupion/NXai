"""Замер качества рерайта: два варианта одного поста, судья вслепую, число на выходе.

Про качество текстов в системе не было ни одного числа. Поменяли персону или модель —
стало лучше или хуже, судили по ощущению от последних просмотренных постов. Это ровно
тот способ, которым люди подтверждают то, во что уже верят: пара удачных постов подряд
после правки промпта убеждает, что правка удалась, а пара неудачных — что нет.

Как устроен замер:

1. **Одинаковый набор исходников.** Берём настоящие посты источников темы — те, что
   уже прошли отбор, то есть тот материал, с которым система и работает. Тексты
   складываются в замер снимком: кандидатов чистят, а замер должен остаться
   проверяемым.
2. **Два варианта каждого поста.** Один — тем, что работает сейчас; второй — тем, что
   проверяют (другая персона, другая модель или и то и другое). Промпт рерайта
   собирается ТОЙ ЖЕ функцией, что в боевом конвейере: собери его замер по-своему,
   сравнивались бы не персоны, а две разные сборки.
3. **Судья не знает, где чей.** Варианты подписаны «Первый» и «Второй», и какой из них
   чей — решает жребий на каждой паре. Скажи мы судье «этот от новой персоны», он
   оценивал бы ожидание, а не текст.
4. **Каждая пара судится дважды, с перестановкой.** Модели свойственно предпочитать
   вариант, показанный первым. Без второго прохода замер измерял бы эту склонность
   вместо качества. Приговоры совпали — победа засчитана; разошлись — ничья: разница
   между текстами оказалась меньше, чем влияние их порядка, и объявлять победителя
   в таком случае значит выдавать шум за результат.

Замер идёт минутами (десятки обращений к модели), поэтому он не ответ на запрос
панели: его заказывают, а выполняет планировщик — так же, как остальную фоновую
работу, и с теми же гарантиями при перезапуске процесса.
"""

import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import CLASSIFICATION_MODEL, REWRITE_MODEL, LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import (
    CandidatePostStatus,
    LlmUsageKind,
    QualityRunStatus,
    QualityVerdict,
)
from core.models.rewrite_quality import RewriteQualityPair, RewriteQualityRun
from core.models.source_channel import SourceChannel
from core.services.llm_budget import ensure_budget
from core.services.llm_usage import record_usage
from core.services.rewrite import build_rewrite_system_prompt

logger = get_logger(__name__)

# Границы размера набора. Меньше пяти — число ни о чём не говорит: при пяти парах
# «3 из 5» получается подбрасыванием монеты. Больше тридцати — это уже сто с лишним
# обращений к модели на один замер, и цена растёт быстрее пользы.
MIN_SIZE = 5
MAX_SIZE = 30
DEFAULT_SIZE = 12

# Модель-судья. Дешёвая намеренно: судейство — это выбор из двух по понятным
# признакам, а не сочинение. Дорогая модель здесь удвоила бы цену замера, не меняя
# выводов.
JUDGE_MODEL = CLASSIFICATION_MODEL

# Сколько текста исходника отдаём судье. Судья сверяет, что факты не переврали;
# для этого хватает начала, а полные простыни удваивают цену судейства.
SOURCE_FOR_JUDGE = 1500

JUDGE_SYSTEM_PROMPT = """\
Ты — придирчивый редактор тематического Telegram-канала. Тебе дают исходный пост \
чужого канала и два варианта, как его переписали для своего канала. Выбери, какой \
вариант лучше подходит для публикации.

Что важно, по убыванию:
1. Факты исходника не переврали и не потеряли главное.
2. Читается как живой текст канала, а не как пересказ: нет канцелярита, нет \
«в данной статье», нет воды.
3. Не копирует исходник дословно и не повторяет его порядок абзацев.
4. Не тащит рекламу автора исходника: чужие упоминания, ссылки, призывы, цены.
5. Длина уместна: не растянуто и не обрублено.

Кто из вариантов чей — тебе неизвестно, и порядок ничего не значит. Не выбирай \
вариант за то, что он длиннее или стоит первым.

Ответь РОВНО в таком виде, без пояснений вокруг:
ПОБЕДИТЕЛЬ: 1 или 2 или НИЧЬЯ
ПОЧЕМУ: одна фраза"""

_WINNER_RE = re.compile(r"ПОБЕДИТЕЛЬ:\s*(1|2|НИЧЬЯ)", re.IGNORECASE)
_REASON_RE = re.compile(r"ПОЧЕМУ:\s*(.+)", re.IGNORECASE | re.DOTALL)


class QualityRunError(Exception):
    """Замер невозможно даже начать — например, у темы нет подходящих исходников."""


@dataclass(frozen=True)
class Judgement:
    """first — победил тот вариант, который показали первым."""

    winner: str  # "first" | "second" | "tie"
    reason: str


def parse_judgement(text: str) -> Judgement:
    """Разбор ответа судьи.

    Непонятный ответ — ничья, а не победа кого-то одного. Судья иногда отвечает
    рассуждением вместо формы; засчитать в таком случае победу по первому
    встреченному в тексте числу значило бы подмешать в замер случайность и не
    заметить этого."""
    match = _WINNER_RE.search(text or "")
    reason_match = _REASON_RE.search(text or "")
    reason = " ".join((reason_match.group(1) if reason_match else "").split())[:300]
    if not match:
        return Judgement(winner="tie", reason=reason or "судья ответил не по форме")
    value = match.group(1).upper()
    if value == "1":
        return Judgement(winner="first", reason=reason)
    if value == "2":
        return Judgement(winner="second", reason=reason)
    return Judgement(winner="tie", reason=reason)


def resolve_pair(direct: QualityVerdict, swapped: QualityVerdict) -> QualityVerdict:
    """Итог пары по двум приговорам.

    Совпали — победа. Разошлись — ничья: значит, судья поменял мнение от одной лишь
    перестановки, и разница между текстами меньше влияния их порядка. Засчитывать
    в таком случае победу первому приговору — значит выдавать шум за результат."""
    return direct if direct == swapped else QualityVerdict.TIE


async def pick_golden_set(session: AsyncSession, theme_id: UUID, size: int) -> list[str]:
    """Исходники для замера — настоящие посты источников этой темы.

    Берём те, что уже прошли отбор (переписаны, ждут проверки, опубликованы): именно
    с таким материалом система и работает. Возьми мы всё подряд, замер бы наполовину
    состоял из постов, которые конвейер и не собирался переписывать.

    Свежие сверху: персону правят под то, что источники пишут сейчас."""
    rows = (
        await session.execute(
            select(CandidatePost.raw_text)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                SourceChannel.theme_id == theme_id,
                CandidatePost.status.in_(
                    [
                        CandidatePostStatus.REWRITTEN,
                        CandidatePostStatus.PENDING_REVIEW,
                        CandidatePostStatus.QUEUED,
                        CandidatePostStatus.PUBLISHED,
                    ]
                ),
                func.length(CandidatePost.raw_text) > 200,
            )
            .order_by(CandidatePost.first_seen_at.desc())
            .limit(size)
        )
    ).scalars().all()
    return [text for text in rows if text]


class RewriteQualityService:
    def __init__(self, session: AsyncSession, llm: LLMClient | None = None) -> None:
        self.session = session
        self.llm = llm or LLMClient()

    async def create_run(
        self,
        *,
        theme_id: UUID,
        title: str,
        baseline_persona: str,
        variant_persona: str,
        baseline_model: str = REWRITE_MODEL,
        variant_model: str = REWRITE_MODEL,
        size: int = DEFAULT_SIZE,
    ) -> RewriteQualityRun:
        """Заказывает замер. Ничего не считает — только откладывает работу.

        Набор исходников снимается ЗДЕСЬ, а не при исполнении: между заказом и
        запуском могут прийти новые посты, и два замера, заказанных подряд,
        сравнивались бы на разных наборах — то есть не сравнивались бы вовсе."""
        size = max(MIN_SIZE, min(size, MAX_SIZE))
        if not baseline_persona.strip() or not variant_persona.strip():
            raise QualityRunError("Обе персоны должны быть заданы — сравнивать не с чем")
        if (baseline_persona.strip() == variant_persona.strip()) and (
            baseline_model == variant_model
        ):
            raise QualityRunError(
                "Варианты одинаковые: разной должна быть либо персона, либо модель"
            )

        sources = await pick_golden_set(self.session, theme_id, size)
        if len(sources) < MIN_SIZE:
            raise QualityRunError(
                f"У темы всего {len(sources)} подходящих исходников, а нужно хотя бы "
                f"{MIN_SIZE}. Соберите постов от источников и повторите."
            )

        run = RewriteQualityRun(
            theme_id=theme_id,
            title=title.strip()[:200],
            baseline_persona=baseline_persona,
            variant_persona=variant_persona,
            baseline_model=baseline_model,
            variant_model=variant_model,
            size=len(sources),
            status=QualityRunStatus.PENDING,
        )
        self.session.add(run)
        await self.session.flush()
        for text in sources:
            self.session.add(RewriteQualityPair(run_id=run.id, source_text=text))
        await self.session.flush()
        return run

    async def execute(self, run: RewriteQualityRun) -> None:
        """Выполняет заказанный замер целиком. Зовётся планировщиком.

        Коммит после каждой пары: замер идёт минутами, и сбой на восьмой паре не
        должен терять первые семь — на них уже потрачены настоящие деньги."""
        run.status = QualityRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await self.session.commit()

        pairs = (
            await self.session.execute(
                select(RewriteQualityPair)
                .where(RewriteQualityPair.run_id == run.id)
                .order_by(RewriteQualityPair.created_at)
            )
        ).scalars().all()

        try:
            for index, pair in enumerate(pairs):
                if pair.verdict is not None:
                    continue  # замер продолжили после перезапуска — пару уже посчитали
                # Потолок расходов проверяем перед каждой парой, а не один раз: замер
                # длинный, и упереться в лимит он может на середине. Тогда честнее
                # остановиться с объяснением, чем молча досчитать сверх лимита.
                await ensure_budget(self.session)
                await self._run_pair(run, pair, seed=index)
                await self.session.commit()

            run.wins_baseline = sum(1 for p in pairs if p.verdict is QualityVerdict.BASELINE)
            run.wins_variant = sum(1 for p in pairs if p.verdict is QualityVerdict.VARIANT)
            run.ties = sum(1 for p in pairs if p.verdict is QualityVerdict.TIE)
            run.status = QualityRunStatus.DONE
            run.finished_at = datetime.now(timezone.utc)
            await self.session.commit()
            logger.info(
                "quality.run_done",
                run_id=str(run.id),
                baseline=run.wins_baseline,
                variant=run.wins_variant,
                ties=run.ties,
            )
        except Exception as exc:
            logger.exception("quality.run_failed", run_id=str(run.id))
            await self.session.rollback()
            run.status = QualityRunStatus.FAILED
            # Текст ошибки показываем человеку как есть: чаще всего это исчерпанный
            # потолок расходов, и он объясняет сам себя.
            run.error = str(exc)[:1000]
            run.finished_at = datetime.now(timezone.utc)
            await self.session.commit()

    async def _run_pair(self, run: RewriteQualityRun, pair: RewriteQualityPair, seed: int) -> None:
        pair.baseline_text = await self._rewrite(
            pair.source_text, run.baseline_persona, run.baseline_model, run.theme_id
        )
        pair.variant_text = await self._rewrite(
            pair.source_text, run.variant_persona, run.variant_model, run.theme_id
        )

        # Модель может отказаться переписывать (в исходнике одна реклама — см.
        # ANTI_COPY_INSTRUCTIONS). Судить такую пару бессмысленно: победит тот, кто
        # хоть что-то написал, а это оценка не качества, а везения с исходником.
        if _is_refusal(pair.baseline_text) or _is_refusal(pair.variant_text):
            pair.verdict_direct = pair.verdict_swapped = pair.verdict = QualityVerdict.TIE
            pair.reason = "в исходнике не оказалось содержания — переписывать было нечего"
            return

        # Жребий на каждой паре: даже с двойным судейством постоянный порядок
        # оставил бы систематический перекос в парах, где судья не поменял мнения.
        rng = random.Random(f"{run.id}-{seed}")
        baseline_first = rng.random() < 0.5

        direct = await self._judge(
            pair.source_text,
            first=pair.baseline_text if baseline_first else pair.variant_text,
            second=pair.variant_text if baseline_first else pair.baseline_text,
            theme_id=run.theme_id,
        )
        swapped = await self._judge(
            pair.source_text,
            first=pair.variant_text if baseline_first else pair.baseline_text,
            second=pair.baseline_text if baseline_first else pair.variant_text,
            theme_id=run.theme_id,
        )

        pair.verdict_direct = _to_verdict(direct.winner, first_is_baseline=baseline_first)
        pair.verdict_swapped = _to_verdict(swapped.winner, first_is_baseline=not baseline_first)
        pair.verdict = resolve_pair(pair.verdict_direct, pair.verdict_swapped)
        pair.reason = direct.reason or swapped.reason

    async def _rewrite(self, source: str, persona: str, model: str, theme_id: UUID | None) -> str:
        result = await self.llm.complete(
            model=model,
            system_prompt=build_rewrite_system_prompt(persona),
            user_prompt=source,
        )
        await record_usage(
            self.session, result, kind=LlmUsageKind.QUALITY, model=model, theme_id=theme_id
        )
        return result.text.strip()

    async def _judge(
        self, source: str, *, first: str, second: str, theme_id: UUID | None
    ) -> Judgement:
        result = await self.llm.complete(
            model=JUDGE_MODEL,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_prompt=(
                f"ИСХОДНЫЙ ПОСТ:\n{source[:SOURCE_FOR_JUDGE]}\n\n"
                f"ВАРИАНТ 1:\n{first}\n\nВАРИАНТ 2:\n{second}"
            ),
            max_tokens=300,
        )
        await record_usage(
            self.session, result, kind=LlmUsageKind.QUALITY, model=JUDGE_MODEL, theme_id=theme_id
        )
        return parse_judgement(result.text)


def _to_verdict(winner: str, *, first_is_baseline: bool) -> QualityVerdict:
    """Приговор «победил первый/второй» переводим в «победил текущий/новый».

    Отдельной функцией, потому что здесь легче всего ошибиться на перестановке: судья
    рассуждает о позициях и ничего не знает про варианты, а замер — наоборот. Имя
    параметра говорит ровно то, что нужно знать: был ли ПЕРВЫМ ПОКАЗАННЫМ текущий
    вариант — а он у прямого и перевёрнутого судейства разный."""
    if winner == "tie":
        return QualityVerdict.TIE
    if winner == "first":
        return QualityVerdict.BASELINE if first_is_baseline else QualityVerdict.VARIANT
    return QualityVerdict.VARIANT if first_is_baseline else QualityVerdict.BASELINE


def _is_refusal(text: str) -> bool:
    """Модель отказалась переписывать либо вернула пустоту."""
    stripped = (text or "").strip()
    return not stripped or stripped.upper().startswith("NO_CONTENT")


def verdict_summary(run: RewriteQualityRun) -> str:
    """Итог словами — его и читает человек, а не три числа.

    Ничьи в знаменателе оставляем: «выиграл в 6 из 12» честнее, чем «в 6 из 8, а про
    остальные умолчим». Отдельно называем случай, когда решающих пар слишком мало,
    чтобы делать вывод, — иначе «2 против 1» читалось бы как победа."""
    decided = run.wins_baseline + run.wins_variant
    total = run.wins_baseline + run.wins_variant + run.ties
    if total == 0:
        return "Нечего сравнивать: ни одной пары."
    if decided < MIN_SIZE:
        return (
            f"Разницы не видно: судья уверенно выбрал только в {decided} парах из {total}. "
            "Похоже, варианты пишут примерно одинаково."
        )
    if run.wins_variant > run.wins_baseline:
        return f"Новый вариант лучше: выиграл {run.wins_variant} из {total} (ничьих {run.ties})."
    if run.wins_baseline > run.wins_variant:
        return (
            f"Текущий вариант лучше: выиграл {run.wins_baseline} из {total} "
            f"(ничьих {run.ties}). Менять не стоит."
        )
    return f"Ровно поровну: {run.wins_baseline} на {run.wins_variant}, ничьих {run.ties}."
