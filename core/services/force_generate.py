"""ForceGenerateService — принудительный внеочередной прогон пайплайна на
одну тему в обход обычного ожидания: докачка истории источников через
Telethon, если свежих кандидатов не хватает (обычный ingest — только live
core/services/ingest_candidates.py, докачки за прошлое пока нет нигде
больше — см. ARCHITECTURE.md §7/ROADMAP.md Phase 1), скоринг без контрольных
точек (+30м/+2ч/+6ч из core/services/scoring.py здесь не ждём), дедуп,
рерайт — «Сделать посты» в панели.

Рерайты уходят в PENDING_REVIEW, а не сразу в REWRITTEN: REWRITTEN —
статус, который core/services/scheduler_pool.py подхватывает для автопаблиша
на ближайшем тике scheduler.py (раз в минуту), а первую партию сгенерированных
вслепую постов оператор должен явно одобрить — см. core/services/review.py."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.embeddings.client import EmbeddingsClient
from core.llm.client import LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole, CandidatePostStatus
from core.models.source_channel import SourceChannel
from core.services.backfill import backfill_source_channel
from core.services.dedup import DedupService
from core.services.persona import build_persona_prompt
from core.services.rewrite import RewriteService

logger = get_logger(__name__)


class ForceGenerateError(Exception):
    """Текст уходит в HTTP-ответ панели как есть."""


@dataclass(frozen=True)
class GeneratedPost:
    candidate_id: UUID
    source_channel_title: str
    rewritten_text: str
    score: float | None


class ForceGenerateService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.llm = LLMClient(settings)
        self.embeddings = EmbeddingsClient(settings)

    async def generate(self, theme_id: UUID, count: int) -> list[GeneratedPost]:
        source_channels = await self._active_source_channels(theme_id)
        if not source_channels:
            raise ForceGenerateError(
                "У темы нет ни одного активного источника с назначенной сессией-читалкой"
            )

        candidates = await self._eligible_candidates(theme_id, count)
        if len(candidates) < count:
            await self._backfill(source_channels)
            candidates = await self._eligible_candidates(theme_id, count)

        if not candidates:
            raise ForceGenerateError(
                "Не нашлось ни одного поста в источниках темы — возможно, каналы пусты "
                "или все посты уже разобраны пайплайном"
            )

        persona_prompt = await self._persona_prompt(theme_id)
        dedup = DedupService(self.session, self.embeddings)
        rewrite = RewriteService(self.session, self.llm, self.embeddings)

        results: list[GeneratedPost] = []
        last_error: str | None = None
        duplicates_found = 0

        for candidate in candidates:
            if len(results) >= count:
                break

            # Скоринг без ожидания контрольных точек — оператор явно запросил
            # рерайт именно сейчас, порог SELECTION_SCORE_THRESHOLD здесь не
            # применяется (это ручной, не автоматический отбор).
            if candidate.score is None:
                candidate.score = 1.0
            candidate.status = CandidatePostStatus.SELECTED
            await self.session.flush()

            try:
                duplicate_of = await dedup.resolve_duplicates(candidate.id, theme_id)
                if duplicate_of is not None:
                    duplicates_found += 1
                    continue
                post_version = await rewrite.generate(candidate.id, persona_prompt)
            except Exception as exc:
                # Не оставляем кандидата застрявшим в SELECTED — частая причина
                # здесь системная (невалидный/неоплаченный ключ LLM/эмбеддингов),
                # а не разовый сбой конкретного поста, так что все следующие
                # кандидаты в этом же вызове почти наверняка упадут тем же
                # образом; возвращаем в очередь, чтобы повторный вызов "Сделать
                # посты" после исправления ключа в Настройках подхватил его снова.
                logger.exception("force_generate.candidate_failed", candidate_id=str(candidate.id))
                candidate.status = CandidatePostStatus.NEW
                await self.session.flush()
                last_error = str(exc)
                continue

            candidate.status = CandidatePostStatus.PENDING_REVIEW
            await self.session.flush()

            source_channel = await self.session.get(SourceChannel, candidate.source_channel_id)
            results.append(
                GeneratedPost(
                    candidate_id=candidate.id,
                    source_channel_title=source_channel.title if source_channel else "",
                    rewritten_text=post_version.rewritten_text,
                    score=candidate.score,
                )
            )

        await self.session.commit()
        logger.info("force_generate.done", theme_id=str(theme_id), generated=len(results))

        if not results:
            if last_error:
                raise ForceGenerateError(
                    f"Не удалось сгенерировать ни одного поста — ошибка: {last_error}. "
                    "Проверьте ключи LLM/эмбеддингов в разделе «Настройки»."
                )
            if duplicates_found:
                raise ForceGenerateError(
                    "Все найденные посты оказались повторами уже обработанных — новых уникальных нет"
                )

        return results

    async def _active_source_channels(self, theme_id: UUID) -> list[SourceChannel]:
        result = await self.session.execute(
            select(SourceChannel).where(
                SourceChannel.theme_id == theme_id,
                SourceChannel.is_active.is_(True),
                SourceChannel.ingest_session_id.is_not(None),
            )
        )
        return list(result.scalars().all())

    async def _eligible_candidates(self, theme_id: UUID, count: int) -> list[CandidatePost]:
        result = await self.session.execute(
            select(CandidatePost)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(
                SourceChannel.theme_id == theme_id,
                CandidatePost.status.in_([CandidatePostStatus.NEW, CandidatePostStatus.SCORING]),
            )
            .order_by(CandidatePost.score.desc().nulls_last(), CandidatePost.first_seen_at.desc())
            .limit(count)
        )
        return list(result.scalars().all())

    async def _backfill(self, source_channels: list[SourceChannel]) -> None:
        """Докачивает недавнюю историю каждого source_channel темы — общая
        логика с фоновым periodic job'ом (scheduler.py:backfill_job), см.
        core/services/backfill.py."""
        for source_channel in source_channels:
            await backfill_source_channel(self.session, source_channel, self.settings)

    async def _persona_prompt(self, theme_id: UUID) -> str:
        result = await self.session.execute(
            select(ChannelBot.persona_config, ChannelBot.persona_prompt).where(
                ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
            )
        )
        row = result.first()
        return build_persona_prompt(row[0], row[1]) if row else ""
