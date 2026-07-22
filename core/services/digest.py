"""AI-дайджест темы (аудит, п.7.1): раз в сутки собирает топ виральных постов
темы за день и просит LLM свести их в один авторский пост-дайджест. Результат
едет по тем же рельсам, что и обычный кандидат (PENDING_REVIEW → одобрение →
автопаблиш) — отдельного механизма публикации не нужно.

Дайджест-кандидат синтетический: привязан к первому источнику темы только
формально (модель требует source_channel_id) и получает отрицательный
tg_message_id, чтобы не столкнуться с реальными сообщениями Telegram (те
всегда положительные) в уникальном ключе (source_channel_id, tg_message_id)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import REWRITE_MODEL, LLMClient
from core.logging import get_logger
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole, CandidatePostStatus
from core.models.post_version import PostVersion
from core.models.source_channel import SourceChannel
from core.services.persona import build_persona_prompt

logger = get_logger(__name__)

DIGEST_LOOKBACK = timedelta(hours=24)
DIGEST_TOP_N = 5
# Статусы, из которых берём материал для дайджеста: всё, что прошло скоринг и
# не отсеяно (свежие NEW ещё без score сюда не попадут — они в порядке отбора).
DIGEST_SOURCE_STATUSES = (
    CandidatePostStatus.SCORING,
    CandidatePostStatus.SELECTED,
    CandidatePostStatus.REWRITTEN,
    CandidatePostStatus.QUEUED,
    CandidatePostStatus.PUBLISHED,
)

DIGEST_INSTRUCTIONS = """\
Ниже — несколько самых заметных постов темы за последние сутки. Составь из них
ОДИН связный авторский пост-дайджест для Telegram-канала:
- начни с короткого вводного предложения-подводки;
- дай 3–5 пунктов, каждый — суть одной новости своими словами, без копирования;
- не ссылайся на источники и не пиши «в этом посте»;
- держись персоны и тона канала (см. системный промпт);
- уложись в 3000 символов, оформи Markdown Telegram (*жирный*, _курсив_).
"""


async def build_digest(
    session: AsyncSession, theme_id: UUID, llm: LLMClient, now: datetime | None = None
) -> UUID | None:
    """Собирает и кладёт дайджест-кандидат в очередь на одобрение. Возвращает
    id кандидата, либо None, если материала за сутки не набралось."""
    now = now or datetime.now(timezone.utc)
    since = now - DIGEST_LOOKBACK

    result = await session.execute(
        select(CandidatePost)
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(
            SourceChannel.theme_id == theme_id,
            CandidatePost.status.in_(DIGEST_SOURCE_STATUSES),
            CandidatePost.score.is_not(None),
            CandidatePost.first_seen_at >= since,
        )
        .order_by(CandidatePost.score.desc())
        .limit(DIGEST_TOP_N)
    )
    top = list(result.scalars().all())
    if not top:
        return None

    # Формальная привязка к источнику темы (модель требует source_channel_id).
    representative_source_id = top[0].source_channel_id

    persona_prompt = await _persona_prompt(session, theme_id)
    joined = "\n\n---\n\n".join(c.raw_text for c in top if c.raw_text)
    system_prompt = f"{persona_prompt}\n\n{DIGEST_INSTRUCTIONS}"
    completion = await llm.complete(model=REWRITE_MODEL, system_prompt=system_prompt, user_prompt=joined)

    digest = CandidatePost(
        source_channel_id=representative_source_id,
        tg_message_id=-int(now.timestamp()),
        raw_text=f"[Дайджест за сутки, {len(top)} пост(ов)]\n\n{joined}",
        first_seen_at=now,
        status=CandidatePostStatus.PENDING_REVIEW,
    )
    session.add(digest)
    await session.flush()
    version = PostVersion(
        candidate_post_id=digest.id,
        variant_no=1,
        rewritten_text=completion.text,
        persona_prompt_used=persona_prompt,
        source_similarity=None,
    )
    session.add(version)
    await session.flush()
    digest.selected_post_version_id = version.id
    await session.flush()

    logger.info("digest.built", theme_id=str(theme_id), candidate_id=str(digest.id), sources=len(top))
    return digest.id


async def _persona_prompt(session: AsyncSession, theme_id: UUID) -> str:
    result = await session.execute(
        select(ChannelBot.persona_config, ChannelBot.persona_prompt).where(
            ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME
        )
    )
    row = result.first()
    return build_persona_prompt(row[0], row[1]) if row else ""
