"""CRUD тем — создание, список, получение и редактирование (переименование,
правка стиля по умолчанию, включение/выключение). Привязка target_channel/
channel_bot к теме делается на своих страницах панели."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole, CandidatePostStatus, PoolPostStatus
from core.models.pool_post import PoolPost
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.theme import Theme
from core.services.panel_settings import get_or_create_panel_settings
from core.services.rubrics import MAX_RUBRICS, RubricError, suggest_rubrics
from core.services.scheduler_pool import resolve_zoneinfo
from interfaces.api.auth import get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/themes", tags=["themes"], dependencies=[Depends(get_current_admin)])


class ThemeOut(BaseModel):
    id: UUID
    name: str
    default_style_prompt: str
    is_active: bool
    digest_enabled: bool
    digest_hour: int
    premoderation: bool
    rubrics: list[str] = []
    manual_mode: bool

    model_config = {"from_attributes": True}


class ThemeCreate(BaseModel):
    name: str
    default_style_prompt: str = ""


class ThemeUpdate(BaseModel):
    """Все поля опциональны — PUT меняет только переданное."""

    name: str | None = None
    default_style_prompt: str | None = None
    is_active: bool | None = None
    digest_enabled: bool | None = None
    digest_hour: int | None = None
    premoderation: bool | None = None
    rubrics: list[str] | None = None
    manual_mode: bool | None = None


@router.get("", response_model=list[ThemeOut])
async def list_themes(session: AsyncSession = Depends(get_db)) -> list[Theme]:
    result = await session.execute(select(Theme).order_by(Theme.name))
    return list(result.scalars().all())


@router.post("", response_model=ThemeOut)
async def create_theme(payload: ThemeCreate, session: AsyncSession = Depends(get_db)) -> Theme:
    theme = Theme(name=payload.name, default_style_prompt=payload.default_style_prompt)
    session.add(theme)
    await session.flush()
    await session.commit()
    return theme


@router.get("/{theme_id}", response_model=ThemeOut)
async def get_theme(theme_id: UUID, session: AsyncSession = Depends(get_db)) -> Theme:
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/{theme_id}", response_model=ThemeOut)
async def update_theme(
    theme_id: UUID, payload: ThemeUpdate, session: AsyncSession = Depends(get_db)
) -> Theme:
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Название темы не может быть пустым")
        theme.name = name
    if payload.default_style_prompt is not None:
        theme.default_style_prompt = payload.default_style_prompt
    if payload.is_active is not None:
        theme.is_active = payload.is_active
    if payload.digest_enabled is not None:
        theme.digest_enabled = payload.digest_enabled
    if payload.digest_hour is not None:
        if not 0 <= payload.digest_hour <= 23:
            raise HTTPException(status_code=400, detail="Час дайджеста должен быть от 0 до 23")
        theme.digest_hour = payload.digest_hour
    if payload.premoderation is not None:
        theme.premoderation = payload.premoderation
    if payload.rubrics is not None:
        theme.rubrics = _clean_rubrics(payload.rubrics)
    if payload.manual_mode is not None:
        theme.manual_mode = payload.manual_mode
        if payload.manual_mode:
            # Выход из автоматического режима гасит незакрытый заказ: иначе
            # тема, только что переведённая в ручной, немедленно принялась бы
            # добирать «долг», которого оператор не заказывал.
            theme.daily_batch_size = 0

    await session.flush()
    await session.commit()
    return theme


def _clean_rubrics(raw: list[str]) -> list[str]:
    """Чистка списка от оператора: пустые, дубли, слишком длинные.

    Дубли режем без учёта регистра — «Деньги» и «деньги» для классификатора
    одна рубрика, но в списке выглядели бы как две, и чередование бы сломалось:
    половина постов ушла бы в одну, половина в другую, а баланс считал бы их
    разными подтемами."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = " ".join(str(item).split())[:64]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        cleaned.append(name)
    if len(cleaned) > MAX_RUBRICS:
        raise HTTPException(
            status_code=400, detail=f"Рубрик не может быть больше {MAX_RUBRICS}"
        )
    return cleaned


class RubricSuggestOut(BaseModel):
    rubrics: list[str]


@router.post("/{theme_id}/rubrics/suggest", response_model=RubricSuggestOut)
async def suggest_theme_rubrics(
    theme_id: UUID, session: AsyncSession = Depends(get_db)
) -> RubricSuggestOut:
    """Подсказка, а не действие: список возвращается в панель, оператор правит
    его руками и сохраняет обычным PUT. Сами по себе рубрики не применяются —
    иначе одна неудачная выдача модели молча переразметила бы тему."""
    try:
        return RubricSuggestOut(rubrics=await suggest_rubrics(session, theme_id))
    except RubricError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ThemeHealthStage(BaseModel):
    key: str
    label: str
    # ok — работает; warn — требует взгляда; crit — конвейер на этом шаге стоит
    status: str
    value: str
    hint: str | None = None


class ThemeHealthOut(BaseModel):
    stages: list[ThemeHealthStage]


@router.get("/{theme_id}/health", response_model=ThemeHealthOut)
async def theme_health(theme_id: UUID, session: AsyncSession = Depends(get_db)) -> ThemeHealthOut:
    """Диагностика «почему тема молчит» одним запросом: шесть шагов конвейера
    (источники → сбор → отбор → рерайт → готовность → публикация), каждый со
    статусом и подсказкой-действием. Заменяет чтение стены алертов: оператор
    видит, на каком именно шаге посты застревают."""
    theme = await session.get(Theme, theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found")

    now = datetime.now(timezone.utc)
    panel_settings = await get_or_create_panel_settings(session)
    tz = resolve_zoneinfo(panel_settings.timezone)
    stages: list[ThemeHealthStage] = []

    # 1. Источники. Три состояния разведены намеренно (UX-аудит, №8): раньше
    # «читалке не назначен источник» и «назначена, но давно молчит» попадали в
    # одну ветку с текстом «сутки без чтения — проверьте аккаунты-читалки», и
    # оператор шёл диагностировать здоровые аккаунты, хотя чинится это
    # выпадающим списком в разделе «Источники» на той же странице. Отдельно
    # «ждёт первого чтения» — норма для только что добавленного источника, а не
    # тревога: строка источника в панели говорит ровно это же, и два разных
    # утверждения об одном факте на одном экране путали больше, чем помогали.
    active_sources = await session.scalar(
        select(func.count())
        .select_from(SourceChannel)
        .where(SourceChannel.theme_id == theme_id, SourceChannel.is_active.is_(True))
    )
    without_session = await session.scalar(
        select(func.count())
        .select_from(SourceChannel)
        .where(
            SourceChannel.theme_id == theme_id,
            SourceChannel.is_active.is_(True),
            SourceChannel.ingest_session_id.is_(None),
        )
    )
    never_scanned = await session.scalar(
        select(func.count())
        .select_from(SourceChannel)
        .where(
            SourceChannel.theme_id == theme_id,
            SourceChannel.is_active.is_(True),
            SourceChannel.ingest_session_id.is_not(None),
            SourceChannel.last_scanned_at.is_(None),
        )
    )
    scanned_recently = await session.scalar(
        select(func.count())
        .select_from(SourceChannel)
        .where(
            SourceChannel.theme_id == theme_id,
            SourceChannel.is_active.is_(True),
            SourceChannel.last_scanned_at >= now - timedelta(hours=24),
        )
    )
    if not active_sources:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="crit", value="нет",
                hint="Добавьте каналы-источники — без них теме неоткуда брать контент",
            )
        )
    elif without_session and without_session == active_sources:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="crit",
                value=f"{active_sources} шт., без читалки",
                hint="Ни одному источнику не назначен аккаунт-читалка — назначьте его "
                     "в разделе «Источники» ниже. Сами аккаунты тут ни при чём",
            )
        )
    elif without_session:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="warn",
                value=f"{active_sources} шт., без читалки {without_session}",
                hint=f"У {without_session} из {active_sources} источников не назначен "
                     "аккаунт-читалка — они не читаются. Назначьте в разделе «Источники» ниже",
            )
        )
    elif not scanned_recently and never_scanned:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="ok",
                value=f"{active_sources} шт., ждут первого чтения",
                hint="Читалка возьмёт их в работу в течение минуты — для только что "
                     "добавленных источников это нормально",
            )
        )
    elif not scanned_recently:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="warn",
                value=f"{active_sources} шт., сутки без чтения",
                hint="Читалка не читала источники больше суток — проверьте на вкладке "
                     "«Аккаунты», что назначенный аккаунт активен",
            )
        )
    else:
        stages.append(
            ThemeHealthStage(
                key="sources", label="Источники", status="ok",
                value=f"{active_sources} шт., читаются",
            )
        )

    # Счётчики кандидатов по статусам одним запросом.
    counts_result = await session.execute(
        select(CandidatePost.status, func.count())
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(SourceChannel.theme_id == theme_id)
        .group_by(CandidatePost.status)
    )
    by_status = {status: count for status, count in counts_result.all()}
    fresh_candidates = await session.scalar(
        select(func.count())
        .select_from(CandidatePost)
        .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
        .where(SourceChannel.theme_id == theme_id, CandidatePost.first_seen_at >= now - timedelta(hours=48))
    )

    # 2. Сбор: приходят ли свежие посты.
    if fresh_candidates:
        stages.append(
            ThemeHealthStage(key="ingest", label="Сбор постов", status="ok", value=f"{fresh_candidates} за 48 ч")
        )
    else:
        stages.append(
            ThemeHealthStage(
                key="ingest", label="Сбор постов", status="warn", value="0 за 48 ч",
                hint="Свежих постов нет — источники молчат или не читаются",
            )
        )

    # 3. Отбор: дозревающие и отобранные.
    maturing = by_status.get(CandidatePostStatus.NEW, 0) + by_status.get(CandidatePostStatus.SCORING, 0)
    selected = by_status.get(CandidatePostStatus.SELECTED, 0)
    stages.append(
        ThemeHealthStage(
            key="scoring", label="Отбор по виральности",
            status="ok" if (maturing or selected) else "warn",
            value=f"дозревают {maturing}, отобрано {selected}",
            hint=None if (maturing or selected) else "Пока нечего отбирать — ждём сбора постов",
        )
    )

    # 4. Рерайт/одобрение.
    ready = by_status.get(CandidatePostStatus.REWRITTEN, 0)
    pending = by_status.get(CandidatePostStatus.PENDING_REVIEW, 0)
    if pending:
        stages.append(
            ThemeHealthStage(
                key="rewrite", label="Рерайт и одобрение", status="warn",
                value=f"готово {ready}, ждут одобрения {pending}",
                hint="Посты ждут вашего решения на странице «Проверка»",
            )
        )
    else:
        stages.append(
            ThemeHealthStage(
                key="rewrite", label="Рерайт и одобрение",
                status="ok" if ready else "warn",
                value=f"готово к выходу {ready}",
                hint=None if ready else "Готовых постов нет — конвейер ещё не дошёл до рерайта",
            )
        )

    # 5. Готовность к публикации: бот + канал.
    bot_active = await session.scalar(
        select(func.count())
        .select_from(ChannelBot)
        .where(ChannelBot.theme_id == theme_id, ChannelBot.role == BotRole.THEME, ChannelBot.is_active.is_(True))
    )
    targets_active = await session.scalar(
        select(func.count())
        .select_from(TargetChannel)
        .where(TargetChannel.theme_id == theme_id, TargetChannel.is_active.is_(True))
    )
    if not bot_active or not targets_active:
        missing = "бота" if not bot_active else "целевого канала"
        stages.append(
            ThemeHealthStage(
                key="publisher", label="Бот и канал", status="crit",
                value=f"нет активного {missing}",
                hint=f"Без этого публиковать некому и некуда — заведите {missing} в разделах ниже",
            )
        )
    else:
        stages.append(
            ThemeHealthStage(
                key="publisher", label="Бот и канал", status="ok",
                value=f"бот активен, каналов: {targets_active}",
            )
        )

    # 6. Публикация: когда выходило в последний раз.
    last_published = await session.scalar(
        select(func.max(Publication.published_at))
        .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
        .where(TargetChannel.theme_id == theme_id)
    )
    pool_ready = await session.scalar(
        select(func.count())
        .select_from(PoolPost)
        .where(PoolPost.theme_id == theme_id, PoolPost.status == PoolPostStatus.READY)
    )
    if last_published is None:
        stages.append(
            ThemeHealthStage(
                key="publications", label="Публикации", status="warn", value="ещё не было",
                hint="Как только появятся готовые посты, бот начнёт публиковать по расписанию",
            )
        )
    elif last_published < now - timedelta(days=3):
        days = (now - last_published).days
        stages.append(
            ThemeHealthStage(
                key="publications", label="Публикации", status="crit",
                value=f"молчит {days} дн.",
                hint="Смотрите, на каком шаге выше конвейер жёлтый/красный — там и застряло",
            )
        )
    else:
        stages.append(
            ThemeHealthStage(
                key="publications", label="Публикации", status="ok",
                # Время в поясе проекта, а не в UTC: в нём же оператор видит
                # прогноз на «Очереди» и в нём считаются тихие часы. Раньше
                # здесь печатался UTC — третий пояс на том же экране
                # (UX-аудит, №11).
                value=f"последняя {last_published.astimezone(tz).strftime('%d.%m %H:%M')}, запас: {pool_ready}",
            )
        )

    return ThemeHealthOut(stages=stages)
