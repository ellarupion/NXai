"""CRUD ботов (тематических и admin) — токены живут в БД (core/models/channel_bot.py),
не в .env, поэтому ввод/смена токена — операция панели, а не SSH. gated
require_superadmin целиком: bot_token — секрет уровня прод-инцидента при утечке."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.client import REWRITE_MODEL, LLMClient
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import DEFAULT_CADENCE, ChannelBot
from core.models.source_channel import SourceChannel
from core.models.enums import AuditAction, BotRole
from core.services.audit import record_audit
from core.services.review import REJECTION_REASONS
from core.services.rewrite import ANTI_COPY_INSTRUCTIONS
from core.services.effective_settings import get_effective_settings
from core.services.persona import build_persona_prompt
from core.services.style_extractor import StyleExtractorError, extract_style_structured
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/channel-bots", tags=["channel-bots"], dependencies=[Depends(require_superadmin)])

# Имена партиал-уникальных индексов из core/models/channel_bot.py — по ним
# отличаем «уже есть активный бот на эту тему» от «уже есть admin-бот», чтобы
# показать оператору осмысленный текст, а не сырой psql-констрейнт.
_ACTIVE_THEME_INDEX = "uq_channel_bots_active_theme"
_ACTIVE_ADMIN_INDEX = "uq_channel_bots_active_admin"


def _uniqueness_message(exc: IntegrityError) -> str:
    detail = str(getattr(exc, "orig", exc))
    if _ACTIVE_THEME_INDEX in detail:
        return "У этой темы уже есть активный бот — отключите старый прежде чем заводить нового"
    if _ACTIVE_ADMIN_INDEX in detail:
        return "Admin-бот уже создан — отредактируйте существующую запись или отключите её"
    return "Нарушено ограничение уникальности бота"


class ChannelBotOut(BaseModel):
    id: UUID
    theme_id: UUID | None
    role: BotRole
    persona_prompt: str
    persona_config: dict
    cadence: dict
    is_active: bool
    token_set: bool
    editor_chat_id: int | None
    use_media: bool
    autopublish_enabled: bool
    # Значим только для role=admin — есть ли получатель уведомлений
    # (см. core/models/channel_bot.py:notify_chat_id,
    # interfaces/bots/handlers/admin_start.py). Для role=theme всегда False.
    notify_chat_set: bool

    model_config = {"from_attributes": True}

    @staticmethod
    def from_model(bot: ChannelBot) -> "ChannelBotOut":
        return ChannelBotOut(
            id=bot.id,
            theme_id=bot.theme_id,
            role=bot.role,
            persona_prompt=bot.persona_prompt,
            persona_config=bot.persona_config,
            cadence=bot.cadence,
            is_active=bot.is_active,
            token_set=bool(bot.bot_token),
            editor_chat_id=bot.editor_chat_id,
            use_media=bot.use_media,
            autopublish_enabled=bot.autopublish_enabled,
            notify_chat_set=bot.notify_chat_id is not None,
        )


class ChannelBotCreate(BaseModel):
    theme_id: UUID | None = None
    role: BotRole = BotRole.THEME
    bot_token: str
    persona_prompt: str = ""
    persona_config: dict = {}
    cadence: dict = DEFAULT_CADENCE

    @model_validator(mode="after")
    def _theme_matches_role(self) -> "ChannelBotCreate":
        if self.role == BotRole.THEME and self.theme_id is None:
            raise ValueError("theme_id обязателен для role=theme")
        if self.role == BotRole.ADMIN and self.theme_id is not None:
            raise ValueError("role=admin не привязывается к теме (theme_id должен быть пустым)")
        return self


class ChannelBotUpdate(BaseModel):
    """Все поля опциональны — PUT меняет только переданное. `bot_token=None`
    значит "не менять токен", в отличие от settings.py здесь нет смысла в
    отдельном "сбросить" — без валидного токена бот нерабочий, обнулять
    незачем."""

    bot_token: str | None = None
    persona_prompt: str | None = None
    persona_config: dict | None = None
    cadence: dict | None = None
    is_active: bool | None = None
    theme_id: UUID | None = None
    # None — не менять; для сброса редактора передаётся editor_chat_id=0.
    editor_chat_id: int | None = None
    use_media: bool | None = None
    autopublish_enabled: bool | None = None


class RejectionStat(BaseModel):
    reason: str
    label: str
    count: int


class RejectionStatsOut(BaseModel):
    days: int
    stats: list[RejectionStat]


class BotCheckOut(BaseModel):
    ok: bool
    detail: str


class ExtractStyleRequest(BaseModel):
    reference_posts: list[str]


class ExtractStyleResponse(BaseModel):
    suggested_persona: str
    # Частичный persona_config для предзаполнения конструктора персоны
    # (tone/tone_custom/length/emoji/address + custom).
    suggested_config: dict = {}


class PreviewRewriteRequest(BaseModel):
    """Песочница: прогнать рерайт с НЕсохранёнными настройками конструктора.
    text не задан — берём последний реальный кандидат-пост темы бота."""

    persona_config: dict | None = None
    persona_prompt: str | None = None
    text: str | None = None


class PreviewRewriteOut(BaseModel):
    original: str
    rewritten: str


@router.get("", response_model=list[ChannelBotOut])
async def list_channel_bots(session: AsyncSession = Depends(get_db)) -> list[ChannelBotOut]:
    result = await session.execute(select(ChannelBot).order_by(ChannelBot.role, ChannelBot.created_at))
    return [ChannelBotOut.from_model(bot) for bot in result.scalars().all()]


@router.post("/extract-style", response_model=ExtractStyleResponse)
async def extract_style_endpoint(
    payload: ExtractStyleRequest, session: AsyncSession = Depends(get_db)
) -> ExtractStyleResponse:
    """StyleExtractor (аудит, п.7.2): по примерам постов LLM предлагает
    persona-промпт. Ничего не сохраняет — оператор вставляет результат в
    персону бота сам."""
    settings = await get_effective_settings(session)
    llm = LLMClient(settings)
    try:
        config = await extract_style_structured(llm, payload.reference_posts)
    except StyleExtractorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Текстовое поле оставляем для обратной совместимости и как читаемое
    # резюме: это custom из структуры (или весь ответ при сбое парсинга).
    return ExtractStyleResponse(
        suggested_persona=config.get("custom", ""), suggested_config=config
    )


@router.post("", response_model=ChannelBotOut)
async def create_channel_bot(
    payload: ChannelBotCreate, session: AsyncSession = Depends(get_db)
) -> ChannelBotOut:
    bot = ChannelBot(
        theme_id=payload.theme_id,
        role=payload.role,
        bot_token=payload.bot_token,
        persona_prompt=payload.persona_prompt,
        persona_config=payload.persona_config,
        cadence=payload.cadence,
    )
    session.add(bot)
    # Единственность (активный THEME на тему / активный ADMIN) держит партиал-
    # индекс в БД — ловим гонку и повтор на уровне констрейнта, а не проверкой
    # select-ом заранее (та не атомарна).
    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=_uniqueness_message(exc)) from exc
    return ChannelBotOut.from_model(bot)


@router.put("/{channel_bot_id}", response_model=ChannelBotOut)
async def update_channel_bot(
    channel_bot_id: UUID, payload: ChannelBotUpdate, session: AsyncSession = Depends(get_db)
) -> ChannelBotOut:
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")

    if payload.bot_token is not None:
        bot.bot_token = payload.bot_token
        await record_audit(session, AuditAction.BOT_TOKEN_CHANGE, "channel_bot", str(bot.id))
    if payload.persona_prompt is not None:
        bot.persona_prompt = payload.persona_prompt
    if payload.persona_config is not None:
        bot.persona_config = payload.persona_config
    if payload.cadence is not None:
        bot.cadence = payload.cadence
    if payload.is_active is not None:
        bot.is_active = payload.is_active
    if payload.editor_chat_id is not None:
        bot.editor_chat_id = payload.editor_chat_id if payload.editor_chat_id != 0 else None
    if payload.use_media is not None:
        bot.use_media = payload.use_media
    if payload.autopublish_enabled is not None:
        bot.autopublish_enabled = payload.autopublish_enabled
    if "theme_id" in payload.model_fields_set:
        if bot.role == BotRole.ADMIN and payload.theme_id is not None:
            raise HTTPException(status_code=400, detail="role=admin не привязывается к теме")
        if bot.role == BotRole.THEME and payload.theme_id is None:
            raise HTTPException(status_code=400, detail="theme_id обязателен для role=theme")
        bot.theme_id = payload.theme_id

    # Реактивация (is_active=True) или смена темы могут столкнуться с уже
    # активным ботом — тот же партиал-индекс ловит это здесь.
    try:
        await session.flush()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=_uniqueness_message(exc)) from exc
    return ChannelBotOut.from_model(bot)


@router.get("/{channel_bot_id}/rejection-stats", response_model=RejectionStatsOut)
async def rejection_stats(
    channel_bot_id: UUID, session: AsyncSession = Depends(get_db)
) -> RejectionStatsOut:
    """Сводка «почему отклоняли» по теме бота за последние 14 дней — сигналы
    для дообучения персоны: «4× канцелярит» — повод добавить компенсирующее
    правило (кнопка в панели)."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from core.models.enums import CandidatePostStatus

    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")
    days = 14
    if bot.theme_id is None:
        return RejectionStatsOut(days=days, stats=[])

    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(CandidatePost.rejection_reason, func.count())
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(
            SourceChannel.theme_id == bot.theme_id,
            CandidatePost.status == CandidatePostStatus.REJECTED,
            CandidatePost.rejection_reason.is_not(None),
            CandidatePost.updated_at >= since,
        )
        .group_by(CandidatePost.rejection_reason)
        .order_by(func.count().desc())
    )
    stats = [
        RejectionStat(reason=reason, label=REJECTION_REASONS.get(reason, reason), count=count)
        for reason, count in result.all()
    ]
    return RejectionStatsOut(days=days, stats=stats)


@router.post("/{channel_bot_id}/preview-rewrite", response_model=PreviewRewriteOut)
async def preview_rewrite(
    channel_bot_id: UUID, payload: PreviewRewriteRequest, session: AsyncSession = Depends(get_db)
) -> PreviewRewriteOut:
    """Песочница конструктора персоны: гоняет реальный рерайт с переданными
    (возможно, ещё не сохранёнными) настройками и возвращает до/после.
    Ничего не пишет в БД — чистый dry-run."""
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")

    original = (payload.text or "").strip()
    if not original:
        if bot.theme_id is None:
            raise HTTPException(status_code=400, detail="У admin-бота нет темы — вставьте текст для проверки сами")
        row = await session.execute(
            select(CandidatePost.raw_text)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(SourceChannel.theme_id == bot.theme_id)
            .order_by(CandidatePost.first_seen_at.desc())
            .limit(1)
        )
        first = row.first()
        if first is None:
            raise HTTPException(
                status_code=400,
                detail="У темы ещё нет собранных постов — вставьте текст для проверки сами",
            )
        original = first[0]

    config = payload.persona_config if payload.persona_config is not None else bot.persona_config
    custom = payload.persona_prompt if payload.persona_prompt is not None else bot.persona_prompt
    persona = build_persona_prompt(config, custom)

    settings = await get_effective_settings(session)
    llm = LLMClient(settings)
    system_prompt = f"{persona}\n\n{ANTI_COPY_INSTRUCTIONS}" if persona else ANTI_COPY_INSTRUCTIONS
    try:
        completion = await llm.complete(
            model=REWRITE_MODEL, system_prompt=system_prompt, user_prompt=original
        )
    except Exception as exc:  # noqa: BLE001 - ошибка LLM уходит оператору как текст
        raise HTTPException(status_code=400, detail=f"Рерайт не удался: {exc}") from exc
    return PreviewRewriteOut(original=original, rewritten=completion.text)


@router.post("/{channel_bot_id}/check", response_model=BotCheckOut)
async def check_channel_bot(
    channel_bot_id: UUID, session: AsyncSession = Depends(get_db)
) -> BotCheckOut:
    """Живая проверка токена через Bot API (getMe) — кнопка «Проверить связь»
    в панели. Отказ Bot API возвращаем как ok=False, а не HTTP-ошибкой: мёртвый
    токен — штатный результат проверки, а не сбой самой ручки."""
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")
    if not bot.bot_token:
        return BotCheckOut(ok=False, detail="Токен не задан")
    from aiogram import Bot as AiogramBot

    tg = AiogramBot(token=bot.bot_token)
    try:
        me = await tg.get_me()
        return BotCheckOut(ok=True, detail=f"На связи: @{me.username}")
    except Exception as exc:  # noqa: BLE001 - любой отказ Bot API = «не на связи»
        return BotCheckOut(ok=False, detail=f"Бот не отвечает: {exc}")
    finally:
        await tg.session.close()


@router.delete("/{channel_bot_id}", status_code=204)
async def delete_channel_bot(
    channel_bot_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    """Полное удаление бота. Процесс ботов подхватит удаление на следующем
    reconcile-тике (hot-reload) и остановит его поллинг без рестарта."""
    bot = await session.get(ChannelBot, channel_bot_id)
    if bot is None:
        raise HTTPException(status_code=404, detail="ChannelBot not found")
    await session.delete(bot)
    await session.commit()
