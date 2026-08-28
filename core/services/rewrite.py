"""RewriteService — LLM-рерайт SELECTED-кандидата под персону темы (см.
ARCHITECTURE.md §5). В отличие от DraftGenerationService в NX (сокращение/
расширение уже готового авторского текста по кнопке редактора), здесь рерайт
обязателен для каждого кандидата и явно нацелен на то, чтобы НЕ повторять
структуру исходного поста — иначе результат легко опознать как копию
источника (см. ROADMAP.md Phase 1)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings.client import EmbeddingsClient
from core.llm.client import REWRITE_MODEL, LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.enums import CandidatePostStatus, LlmUsageKind
from core.models.post_version import PostVersion
from core.models.source_channel import SourceChannel
from core.services.content_filter import is_too_short_to_rewrite
from core.services.llm_usage import UsageRecord, record_usage
from core.services.post_passport import merge_passport, persona_summary, rewrite_facts
from core.services.trust_score import TrustEvent, adjust_trust_score

logger = get_logger(__name__)


class RewriteError(Exception):
    """Рерайт невозможен по содержанию исходника, а не из-за сбоя."""

ANTI_COPY_INSTRUCTIONS = """\
Перепиши пост своими словами для тематического Telegram-канала. Требования:
- не сохраняй порядок абзацев и зачин исходного текста — переставь факты;
- не копируй формулировки дословно, кроме имён/цифр/названий;
- подстрой длину и тон под персону канала (см. системный промпт);
- не добавляй ссылки/упоминания исходного канала;
- ВЫРЕЖИ всё, что продвигает автора исходника: чужие @упоминания и ссылки,
  призывы записаться/писать в личку, цены, промокоды, анонсы его курсов и
  встреч, условия вида «N реакций — и выложу продолжение». Если после
  вырезания остаётся только реклама и полезного содержания нет — верни ровно
  строку NO_CONTENT и ничего больше;
- итог не длиннее 3500 символов: у Telegram жёсткий лимит 4096 на сообщение,
  и к тексту ещё добавляется подпись канала;
- разметку оформляй в Markdown Telegram: *жирный*, _курсив_, [текст](ссылка).
  Не используй заголовки # и таблицы — Telegram их не поддерживает; следи,
  чтобы * и _ были парными, иначе разметка не отрендерится.
"""


class RewriteService:
    def __init__(self, session: AsyncSession, llm: LLMClient, embeddings: EmbeddingsClient) -> None:
        self.session = session
        self.llm = llm
        self.embeddings = embeddings
        # Снимок расхода последнего вызова. Нужен вызывающему на случай, когда его
        # транзакция откатится уже после того, как модель отработала и деньги списаны
        # (см. core/services/llm_usage.py:UsageRecord).
        self.last_usage: UsageRecord | None = None

    async def generate(
        self, candidate_id: UUID, persona_prompt: str, origin: str | None = None
    ) -> PostVersion:
        candidate = await self.session.get(CandidatePost, candidate_id)
        if candidate is None:
            raise ValueError(f"CandidatePost {candidate_id} not found")
        if candidate.status is not CandidatePostStatus.SELECTED:
            raise ValueError(f"CandidatePost {candidate.id} is {candidate.status.value}, expected selected")
        # Вторая линия обороны к отсеву на приёме (content_filter): с пустым
        # user_prompt модель отвечает не постом, а репликой «дай мне текст», и
        # эта реплика уходит редактору как готовый пост. Лучше явная ошибка.
        if is_too_short_to_rewrite(candidate.raw_text):
            raise RewriteError(
                "В исходном посте нет текста — переписывать нечего "
                "(пост-картинка без подписи)"
            )

        system_prompt = f"{persona_prompt}\n\n{ANTI_COPY_INSTRUCTIONS}"
        result = await self.llm.complete(
            model=REWRITE_MODEL,
            system_prompt=system_prompt,
            user_prompt=candidate.raw_text,
        )
        # Расход пишем СРАЗУ, до проверок ниже. Модель уже отработала и деньги уже
        # списаны: если ниже мы откажемся от поста (только реклама, слишком похоже на
        # исходник), расход всё равно был. Снимок кладём в last_usage — вызывающий
        # может переписать его в чистой сессии, если его транзакция откатится.
        self.last_usage = await record_usage(
            self.session,
            result,
            kind=LlmUsageKind.REWRITE,
            model=REWRITE_MODEL,
            entity_id=candidate_id,
            # Тему берём через источник: расход надо уметь разложить по темам, иначе
            # общий итог не отвечает на вопрос «какая тема столько ест».
            theme_id=await self.session.scalar(
                select(SourceChannel.theme_id).where(
                    SourceChannel.id == candidate.source_channel_id
                )
            ),
        )

        # Модель сама сообщает, что вырезать было нечего, кроме рекламы
        # (см. ANTI_COPY_INSTRUCTIONS). Ловим здесь, а не отдаём редактору
        # пустышку: эвристический фильтр на приёме ловит явное, а это — сеть
        # для завуалированной продажи, которая по маркерам не опозналась.
        if result.text.strip().upper().startswith("NO_CONTENT"):
            logger.info("rewrite.only_promo", candidate_id=str(candidate_id))
            raise RewriteError(
                "В исходном посте нет ничего, кроме рекламы автора — публиковать нечего"
            )

        source_similarity = await self._similarity(candidate.raw_text, result.text)

        # Не candidate.versions (ленивая relationship — синхронный доступ к ней
        # под asyncpg падает MissingGreenlet, раз объект не был явно предзагружен
        # selectinload/joinedload): считаем напрямую запросом.
        existing_versions = await self.session.scalar(
            select(func.count()).select_from(PostVersion).where(PostVersion.candidate_post_id == candidate.id)
        )
        variant_no = (existing_versions or 0) + 1
        version = PostVersion(
            candidate_post_id=candidate.id,
            variant_no=variant_no,
            rewritten_text=result.text,
            persona_prompt_used=persona_prompt,
            source_similarity=source_similarity,
        )
        self.session.add(version)
        await self.session.flush()

        candidate.selected_post_version_id = version.id
        candidate.status = CandidatePostStatus.REWRITTEN
        await self.session.flush()
        # Источник исправно поставляет рерайтабельный контент — единственное
        # место бонуса за успех (core/services/force_generate.py тоже проходит
        # через этот метод, а затем сам переводит статус в PENDING_REVIEW —
        # дублировать бонус в core/services/review.py:approve_candidate не нужно).
        await adjust_trust_score(self.session, candidate.source_channel_id, TrustEvent.SUCCESS)

        await merge_passport(self.session, candidate_id, rewrite_facts(
            model=REWRITE_MODEL,
            persona_summary=persona_summary(persona_prompt),
            source_length=len(candidate.raw_text or ""),
            result_length=len(result.text),
            variant_no=variant_no,
            source_similarity=source_similarity,
        ))
        # origin переопределяет засев отбора: пост, заказанный оператором, порога не
        # проходил вовсе, и написать туда действующий порог значило бы соврать.
        if origin is not None:
            await merge_passport(self.session, candidate_id, {"origin": origin})

        logger.info(
            "rewrite.generated",
            candidate_id=str(candidate_id),
            post_version_id=str(version.id),
            source_similarity=source_similarity,
        )
        return version

    async def _similarity(self, raw_text: str, rewritten_text: str) -> float | None:
        """embedding-дистанция рерайта от оригинала — метрика анти-плагиата
        (см. core/models/post_version.py:PostVersion.source_similarity),
        считается той же моделью, что и дедуп, без отдельного вызова pgvector:
        для пары текстов проще посчитать косинус в Python, чем гонять через БД.

        Без Voyage-ключа возвращает None — это необязательная метрика контроля
        качества, а не то, от чего зависит сам рерайт (core/embeddings/client.py:
        is_configured)."""
        if not self.embeddings.is_configured:
            return None
        raw_embedding, rewritten_embedding = await self.embeddings.embed([raw_text, rewritten_text])
        return _cosine_similarity(raw_embedding, rewritten_embedding)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
