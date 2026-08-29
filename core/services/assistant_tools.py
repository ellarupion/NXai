"""Инструменты помощника — всё, что он умеет узнать о системе. Только чтение.

Почему инструменты, а не «положим всё в промпт». Вопросы владельца заранее
неизвестны: «почему сегодня мало постов», «на что ушли деньги за неделю», «какой
источник перестал давать выхлоп» — под каждый нужны свои данные, а класть в каждый
запрос всё сразу дорого и всё равно мало. Модель сама берёт то, что нужно этому
вопросу.

Только чтение — это устройство, а не обещание. Здесь нет ни одной функции, которая
что-то меняет: помощник не может одобрить пост, выключить тему или потратить деньги
на рерайт. Одобрение и публикация остаются кнопками в панели и в боте. Появись здесь
хоть один изменяющий инструмент — и чужой текст, который приходит в эти же ответы из
чужих каналов, получил бы шанс сработать как просьба владельца.

У каждого ответа две части: text уходит модели, summary — человеку. Панель под
ответом показывает, что именно помощник смотрел, — без этого нельзя отличить ответ,
посчитанный по данным, от придуманного по памяти.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.audit_log import AuditLog
from core.models.candidate_post import CandidatePost
from core.models.channel_bot import ChannelBot
from core.models.enums import BotRole, CandidatePostStatus, PublicationSource
from core.models.post_passport import PostPassport
from core.models.metrics_snapshot import PublicationMetricsSnapshot
from core.models.post_version import PostVersion
from core.models.publication import Publication
from core.models.source_channel import SourceChannel
from core.models.target_channel import TargetChannel
from core.models.theme import Theme
from core.services.automation import AutomationSettings
from core.services.llm_usage import summary_by_day, summary_by_kind, summary_by_theme

logger = get_logger(__name__)

# Сколько строк максимум отдаём за один вызов. Потолок нужен не ради скорости, а ради
# денег: каждая строка — токены в следующем запросе к модели, и «покажи все посты»
# на живой базе — это десятки тысяч токенов на вопрос, ответ на который считается
# одним запросом к базе.
MAX_ROWS = 40

# Потолок на весь вопрос. Модель, которой велено «посчитай точно», склонна листать
# страницу за страницей; без общего потолка один вопрос обходится в разы дороже, чем
# стоит ответ.
TOOL_OUTPUT_BUDGET_CHARS = 60_000

# Сколько знаков текста поста показываем. Целиком нужны редкие вопросы про
# формулировки, а платим за них на каждом вызове.
TEXT_PREVIEW = 400

STATUS_TITLES: dict[CandidatePostStatus, str] = {
    CandidatePostStatus.NEW: "только увиден",
    CandidatePostStatus.SCORING: "набирает метрики",
    CandidatePostStatus.SELECTED: "отобран, ждёт рерайта",
    CandidatePostStatus.REWRITTEN: "переписан, ждёт слота",
    CandidatePostStatus.PENDING_REVIEW: "ждёт проверки",
    CandidatePostStatus.QUEUED: "взят в публикацию",
    CandidatePostStatus.PUBLISHED: "опубликован",
    CandidatePostStatus.REJECTED: "отклонён",
    CandidatePostStatus.DUPLICATE: "дубль",
}


@dataclass(frozen=True)
class ToolResult:
    text: str
    summary: str


class ToolError(Exception):
    """Инструмент позвали с параметрами, которых нет (несуществующая тема, период
    задом наперёд). Текст ошибки уходит модели — она исправится и позовёт снова."""


def post_code(candidate_id: UUID) -> str:
    """Короткий код поста для разговора. Полный UUID модель гоняет туда-сюда целиком,
    тратит на него токены и ошибается символом; восьми шестнадцатеричных знаков хватает,
    чтобы различить посты, которых в базе тысячи."""
    return candidate_id.hex[:8]


async def resolve_post_code(session: AsyncSession, code: str) -> UUID:
    """Код обратно в идентификатор. Ищем по началу текстового представления UUID:
    первые восемь знаков кода — это ровно первая группа UUID до дефиса."""
    code = (code or "").strip().lower().replace("-", "")
    if len(code) != 8 or any(ch not in "0123456789abcdef" for ch in code):
        raise ToolError(f"«{code}» не похож на код поста — нужны восемь знаков вида 3f2b1a90")
    found = (
        await session.execute(
            select(CandidatePost.id).where(
                cast(CandidatePost.id, String).like(f"{code}-%")
            )
        )
    ).scalars().all()
    if not found:
        raise ToolError(
            f"Поста с кодом {code} нет. Код берётся из ответа инструмента, придумывать его нельзя."
        )
    return found[0]


def _fmt_int(value: int | None) -> str:
    return f"{value:,}".replace(",", " ") if value is not None else "—"


def _preview(text: str | None, limit: int = TEXT_PREVIEW) -> str:
    clean = " ".join((text or "").split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _parse_day(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ToolError(f"{field} должен быть в виде ГГГГ-ММ-ДД, а пришло «{value}»") from exc


# Описания для модели — формат OpenAI, litellm сам переводит его в формат Anthropic.
TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "themes_overview",
            "description": (
                "Все темы: включена ли, ручной ли режим, сколько источников и целевых "
                "каналов, сколько постов ждёт проверки, какое дневное расписание у бота, "
                "какие заданы подтемы. Отсюда начинай ответ на вопросы вида «почему тема "
                "молчит» или «почему мало постов»."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pipeline",
            "description": (
                "Сколько постов на каждой стадии конвейера и за какой срок они пришли: "
                "увидено, набирает метрики, отобрано, переписано, ждёт проверки, "
                "опубликовано, отклонено, дубли. Показывает, где именно конвейер встал."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "description": "Название темы. Без него — по всем."},
                    "days": {"type": "integer", "description": "За сколько последних дней считать. По умолчанию 7."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue",
            "description": (
                "Что прямо сейчас ждёт проверки: тема, источник, подтема, виральность, "
                "начало переписанного текста и код поста. По коду можно спросить разбор "
                "через post_passport."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "description": "Название темы."},
                    "limit": {"type": "integer", "description": f"Сколько строк, максимум {MAX_ROWS}."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publications",
            "description": (
                "Что вышло в каналы: когда, куда, из какого источника, подтема, просмотры "
                "и пересылки, начало текста и код поста. Этим отвечай на вопросы «что "
                "зашло» и «что выходило на этой неделе»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "day_from": {"type": "string", "description": "Начало периода, ГГГГ-ММ-ДД."},
                    "day_to": {"type": "string", "description": "Конец периода включительно, ГГГГ-ММ-ДД."},
                    "sort": {
                        "type": "string",
                        "enum": ["recent", "forwards", "views"],
                        "description": "Порядок: свежие сверху (по умолчанию), по пересылкам, по просмотрам.",
                    },
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sources",
            "description": (
                "Источники: к какой теме относится, включён ли, доверие, когда последний "
                "раз читался, сколько постов дал и сколько из них дошло до публикации. "
                "Отсюда видно, какой источник перестал давать выхлоп."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spend",
            "description": (
                "Расходы на ИИ: сколько всего за период, по разделам работы, по дням и по "
                "темам, а также дневной потолок и сколько от него уже потрачено сегодня."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "За сколько дней. По умолчанию 7."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "settings_overview",
            "description": (
                "Действующие пороги и времена поведения: порог отбора, ширина пула, "
                "границы доверия источникам, порог схожести для дедупа, дневной потолок "
                "расходов. Нужен, чтобы объяснить, ПОЧЕМУ система ведёт себя так."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_passport",
            "description": (
                "Разбор одного поста по коду: почему выбран, какой был скор и порог, чем "
                "переписан, какая подтема и по чему её решали, что поправил редактор, "
                "куда вышел."
            ),
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Код поста, восемь знаков."}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "actions_log",
            "description": (
                "Журнал действий: кто что делал в панели и в боте — одобрения, "
                "отклонения, правки, заказы постов, смена настроек и ключей."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "days": {"type": "integer", "description": "За сколько дней. По умолчанию 7."},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
]

TOOL_NAMES = {spec["function"]["name"] for spec in TOOL_SPECS}


class AssistantToolbox:
    """Исполнитель инструментов. Ничего не меняет — см. заголовок модуля."""

    def __init__(self, session: AsyncSession, *, automation: AutomationSettings) -> None:
        self.session = session
        self.automation = automation
        # Сколько знаков данных уже отдано модели по этому вопросу — см. run().
        self.spent_chars = 0

    async def run(self, name: str, args: dict) -> ToolResult:
        if self.spent_chars >= TOOL_OUTPUT_BUDGET_CHARS:
            return ToolResult(
                text=(
                    "Лимит выборки на этот вопрос исчерпан — данных прочитано достаточно. "
                    "Ответь по собранному и предупреди, что смотрел не всё."
                ),
                summary="лимит выборки исчерпан",
            )

        handlers = {
            "themes_overview": self._themes_overview,
            "pipeline": self._pipeline,
            "queue": self._queue,
            "publications": self._publications,
            "sources": self._sources,
            "spend": self._spend,
            "settings_overview": self._settings_overview,
            "post_passport": self._post_passport,
            "actions_log": self._actions_log,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"Инструмента «{name}» нет. Доступны: {', '.join(sorted(TOOL_NAMES))}.")

        result = await handler(args)
        self.spent_chars += len(result.text)
        return result

    # --- вспомогательное ---------------------------------------------------

    async def _theme_by_name(self, name: str | None) -> Theme | None:
        """Тему ищем по названию, а не по идентификатору: модель видит названия и
        оперирует ими. Совпадение нестрогое — «финансы» найдёт «Финансы и рынки»."""
        if not name:
            return None
        needle = name.strip().lower()
        themes = (await self.session.execute(select(Theme))).scalars().all()
        exact = [t for t in themes if t.name.lower() == needle]
        if exact:
            return exact[0]
        partial = [t for t in themes if needle in t.name.lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise ToolError(
                f"«{name}» подходит сразу нескольким темам: {', '.join(t.name for t in partial)}. "
                "Назови точнее."
            )
        known = ", ".join(t.name for t in themes) or "их пока нет"
        raise ToolError(f"Темы «{name}» нет. Есть: {known}.")

    def _limit(self, args: dict) -> int:
        raw = args.get("limit")
        return max(1, min(int(raw), MAX_ROWS)) if isinstance(raw, int) else MAX_ROWS

    def _days(self, args: dict, default: int = 7) -> int:
        raw = args.get("days")
        return max(1, min(int(raw), 365)) if isinstance(raw, int) else default

    def _period(self, args: dict) -> tuple[datetime, datetime]:
        """Границы периода из day_from/day_to. Конец включительный: «по 5 августа»
        человек понимает как «включая весь пятый», а не «до полуночи пятого»."""
        day_from = _parse_day(args.get("day_from"), "day_from")
        day_to = _parse_day(args.get("day_to"), "day_to")
        if day_from and day_to and day_from > day_to:
            raise ToolError("Начало периода позже конца — поменяй day_from и day_to местами.")
        end = (
            datetime.combine(day_to, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
            if day_to
            else datetime.now(timezone.utc)
        )
        start = (
            datetime.combine(day_from, datetime.min.time(), tzinfo=timezone.utc)
            if day_from
            else end - timedelta(days=self._days(args, 7))
        )
        return start, end

    # --- инструменты -------------------------------------------------------

    async def _themes_overview(self, args: dict) -> ToolResult:
        themes = (await self.session.execute(select(Theme).order_by(Theme.name))).scalars().all()
        if not themes:
            return ToolResult(text="Тем пока нет.", summary="темы — пусто")

        sources = dict(
            (
                await self.session.execute(
                    select(SourceChannel.theme_id, func.count())
                    .where(SourceChannel.is_active.is_(True))
                    .group_by(SourceChannel.theme_id)
                )
            ).all()
        )
        targets = dict(
            (
                await self.session.execute(
                    select(TargetChannel.theme_id, func.count())
                    .where(TargetChannel.is_active.is_(True))
                    .group_by(TargetChannel.theme_id)
                )
            ).all()
        )
        pending = dict(
            (
                await self.session.execute(
                    select(SourceChannel.theme_id, func.count())
                    .join(CandidatePost, CandidatePost.source_channel_id == SourceChannel.id)
                    .where(CandidatePost.status == CandidatePostStatus.PENDING_REVIEW)
                    .group_by(SourceChannel.theme_id)
                )
            ).all()
        )
        bots = {
            b.theme_id: b
            for b in (
                await self.session.execute(select(ChannelBot).where(ChannelBot.role == BotRole.THEME))
            ).scalars().all()
        }

        lines = []
        for t in themes:
            bot = bots.get(t.id)
            cadence = bot.cadence if bot else {}
            per_day = cadence.get("posts_per_day_target", "—") if isinstance(cadence, dict) else "—"
            lines.append(
                f"- {t.name}: {'включена' if t.is_active else 'ВЫКЛЮЧЕНА'}, "
                f"{'ручной режим (посты только по просьбе)' if t.manual_mode else 'непрерывный конвейер'}, "
                f"источников {sources.get(t.id, 0)}, каналов {targets.get(t.id, 0)}, "
                f"ждёт проверки {pending.get(t.id, 0)}, расписание {per_day} постов в день, "
                f"бот {'есть' if bot else 'НЕ ЗАВЕДЁН'}"
                f"{', автопубликация включена' if bot and bot.autopublish_enabled else ''}, "
                f"подтемы: {', '.join(t.rubrics) if t.rubrics else 'не заданы'}"
            )
        return ToolResult(text="\n".join(lines), summary=f"обзор тем — {len(themes)}")

    async def _pipeline(self, args: dict) -> ToolResult:
        theme = await self._theme_by_name(args.get("theme"))
        days = self._days(args)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt: Select = (
            select(CandidatePost.status, func.count())
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .where(CandidatePost.first_seen_at >= since)
            .group_by(CandidatePost.status)
        )
        if theme:
            stmt = stmt.where(SourceChannel.theme_id == theme.id)
        rows = (await self.session.execute(stmt)).all()
        counts = {status: count for status, count in rows}

        last_seen = await self.session.scalar(
            select(func.max(CandidatePost.first_seen_at)).select_from(CandidatePost)
        )
        where = f" по теме «{theme.name}»" if theme else ""
        if not counts:
            return ToolResult(
                text=(
                    f"За последние {days} дн.{where} ни одного поста от источников не пришло. "
                    + (
                        f"Последний раз пост приходил {last_seen:%d.%m.%Y %H:%M} UTC."
                        if last_seen
                        else "Постов от источников не было вообще ни разу."
                    )
                ),
                summary=f"конвейер за {days} дн. — пусто",
            )
        lines = [
            f"- {STATUS_TITLES.get(status, status.value)}: {count}"
            for status, count in sorted(counts.items(), key=lambda kv: -kv[1])
        ]
        total = sum(counts.values())
        return ToolResult(
            text=f"Постов за {days} дн.{where}: {total}\n" + "\n".join(lines),
            summary=f"конвейер за {days} дн.{where} — {total}",
        )

    async def _queue(self, args: dict) -> ToolResult:
        theme = await self._theme_by_name(args.get("theme"))
        limit = self._limit(args)
        stmt = (
            select(CandidatePost, SourceChannel, PostVersion, Theme.name)
            .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .outerjoin(Theme, Theme.id == SourceChannel.theme_id)
            .outerjoin(PostVersion, PostVersion.id == CandidatePost.selected_post_version_id)
            .where(CandidatePost.status == CandidatePostStatus.PENDING_REVIEW)
            .order_by(CandidatePost.score.desc().nullslast())
        )
        if theme:
            stmt = stmt.where(SourceChannel.theme_id == theme.id)
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = (await self.session.execute(stmt.limit(limit))).all()
        if not rows:
            return ToolResult(text="Очередь проверки пуста.", summary="очередь — пусто")
        lines = []
        for c, src, version, th in rows:
            head = f"[{post_code(c.id)}] {th or 'без темы'} · {src.title}"
            if c.rubric:
                head += f" · {c.rubric}"
            if c.score is not None:
                head += f" · виральность {c.score:.2f}"
            lines.append(f"- {head}\n  {_preview(version.rewritten_text if version else c.raw_text)}")
        shown = f", показано {len(rows)}" if total and total > len(rows) else ""
        return ToolResult(
            text=f"Ждут проверки: {total}{shown}\n" + "\n".join(lines),
            summary=f"очередь — {total}{shown}",
        )

    async def _publications(self, args: dict) -> ToolResult:
        theme = await self._theme_by_name(args.get("theme"))
        start, end = self._period(args)
        limit = self._limit(args)

        latest = (
            select(
                PublicationMetricsSnapshot.publication_id,
                func.max(PublicationMetricsSnapshot.taken_at).label("latest_at"),
            )
            .group_by(PublicationMetricsSnapshot.publication_id)
            .subquery()
        )
        stmt = (
            select(
                Publication,
                Theme.name,
                TargetChannel.title,
                PostVersion.rewritten_text,
                CandidatePost.id,
                CandidatePost.rubric,
                SourceChannel.title,
                PublicationMetricsSnapshot.views,
                PublicationMetricsSnapshot.forwards,
            )
            .join(TargetChannel, TargetChannel.id == Publication.target_channel_id)
            .join(Theme, Theme.id == TargetChannel.theme_id)
            .outerjoin(PostVersion, PostVersion.id == Publication.post_version_id)
            .outerjoin(CandidatePost, CandidatePost.id == PostVersion.candidate_post_id)
            .outerjoin(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
            .outerjoin(latest, latest.c.publication_id == Publication.id)
            .outerjoin(
                PublicationMetricsSnapshot,
                (PublicationMetricsSnapshot.publication_id == Publication.id)
                & (PublicationMetricsSnapshot.taken_at == latest.c.latest_at),
            )
            .where(Publication.published_at >= start, Publication.published_at < end)
        )
        if theme:
            stmt = stmt.where(Theme.id == theme.id)

        sort = args.get("sort") or "recent"
        order = {
            "recent": Publication.published_at.desc(),
            "forwards": PublicationMetricsSnapshot.forwards.desc().nullslast(),
            "views": PublicationMetricsSnapshot.views.desc().nullslast(),
        }.get(sort, Publication.published_at.desc())

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = (await self.session.execute(stmt.order_by(order).limit(limit))).all()
        period = f"{start:%d.%m.%Y}–{(end - timedelta(seconds=1)):%d.%m.%Y}"
        if not rows:
            return ToolResult(
                text=f"За {period} публикаций не было.", summary=f"публикации {period} — 0"
            )
        lines = []
        for pub, th, ch, rewritten, cand_id, rubric, src, views, forwards in rows:
            head = f"{pub.published_at:%d.%m %H:%M} · {th} · {ch}"
            if cand_id:
                head = f"[{post_code(cand_id)}] " + head
            if src:
                head += f" · из «{src}»"
            if rubric:
                head += f" · {rubric}"
            if pub.source is PublicationSource.POOL:
                head += " · из своего запаса"
            if pub.is_ad_cover:
                head += " · перекрытие рекламы"
            head += f" · просмотры {_fmt_int(views)}, пересылки {_fmt_int(forwards)}"
            lines.append(f"- {head}\n  {_preview(rewritten)}")
        shown = f", показано {len(rows)}" if total and total > len(rows) else ""
        return ToolResult(
            text=f"Публикаций за {period}: {total}{shown}\n" + "\n".join(lines),
            summary=f"публикации {period} — {total}{shown}",
        )

    async def _sources(self, args: dict) -> ToolResult:
        theme = await self._theme_by_name(args.get("theme"))
        limit = self._limit(args)
        stmt = (
            select(SourceChannel, Theme.name)
            .outerjoin(Theme, Theme.id == SourceChannel.theme_id)
            .order_by(SourceChannel.title)
        )
        if theme:
            stmt = stmt.where(SourceChannel.theme_id == theme.id)
        rows = (await self.session.execute(stmt.limit(limit))).all()
        if not rows:
            return ToolResult(text="Источников нет.", summary="источники — пусто")

        given = dict(
            (
                await self.session.execute(
                    select(CandidatePost.source_channel_id, func.count()).group_by(
                        CandidatePost.source_channel_id
                    )
                )
            ).all()
        )
        published = dict(
            (
                await self.session.execute(
                    select(CandidatePost.source_channel_id, func.count())
                    .where(CandidatePost.status == CandidatePostStatus.PUBLISHED)
                    .group_by(CandidatePost.source_channel_id)
                )
            ).all()
        )
        lines = []
        for src, th in rows:
            last = f"{src.last_scanned_at:%d.%m %H:%M}" if src.last_scanned_at else "никогда"
            lines.append(
                f"- {src.title} ({th or 'тема не назначена'}): "
                f"{'включён' if src.is_active else 'ВЫКЛЮЧЕН'}, доверие {src.trust_score:.2f}, "
                f"читался {last}, дал постов {given.get(src.id, 0)}, "
                f"из них опубликовано {published.get(src.id, 0)}"
            )
        return ToolResult(text="\n".join(lines), summary=f"источники — {len(rows)}")

    async def _spend(self, args: dict) -> ToolResult:
        days = self._days(args)
        by_kind = await summary_by_kind(self.session, days)
        by_day = await summary_by_day(self.session, days)
        by_theme = await summary_by_theme(self.session, days)
        total = sum(k.cost_usd for k in by_kind)

        parts = [f"Всего за {days} дн.: ${total:.4f}"]
        parts.append(f"Дневной потолок: ${self.automation.daily_budget_usd:.2f}")
        if by_kind:
            parts.append("По разделам:")
            parts += [f"- {k.title}: ${k.cost_usd:.4f} за {k.calls} вызовов" for k in by_kind]
        if by_theme:
            parts.append("По темам:")
            parts += [f"- {t.theme_name}: ${t.cost_usd:.4f}" for t in by_theme]
        if by_day:
            parts.append("По дням: " + ", ".join(f"{d.day} ${d.cost_usd:.4f}" for d in by_day))
        return ToolResult(text="\n".join(parts), summary=f"расходы за {days} дн. — ${total:.4f}")

    async def _settings_overview(self, args: dict) -> ToolResult:
        a = self.automation
        return ToolResult(
            text=(
                f"Порог отбора: {a.selection_score_threshold}× медианы канала\n"
                f"Постов для медианы: {a.min_samples_for_median}\n"
                f"Ширина пула отбора: {a.selection_pool_factor}× заказа\n"
                f"Доверие источникам: от {a.min_trust_score} до {a.max_trust_score}\n"
                f"Порог схожести для дедупа: {a.dedup_similarity_threshold}\n"
                f"Минимальная длина поста для рерайта: {a.min_rewritable_length} знаков\n"
                f"Дневной потолок расходов: ${a.daily_budget_usd}\n"
                f"Предупреждать при: {a.budget_warn_percent}% потолка\n"
                f"Максимальный размер партии на день: {a.max_daily_batch}\n"
                f"Задержка перекрытия рекламы: {a.ad_cover_delay_minutes} мин."
            ),
            summary="действующие пороги",
        )

    async def _post_passport(self, args: dict) -> ToolResult:
        code = args.get("code") or ""
        candidate_id = await resolve_post_code(self.session, code)
        row = (
            await self.session.execute(
                select(CandidatePost, SourceChannel.title, Theme.name, PostPassport.data)
                .join(SourceChannel, SourceChannel.id == CandidatePost.source_channel_id)
                .outerjoin(Theme, Theme.id == SourceChannel.theme_id)
                .outerjoin(PostPassport, PostPassport.candidate_post_id == CandidatePost.id)
                .where(CandidatePost.id == candidate_id)
            )
        ).first()
        if row is None:
            raise ToolError(f"Поста с кодом {code} нет.")
        candidate, src, th, data = row
        facts = data or {}
        lines = [
            f"Пост [{post_code(candidate.id)}] — {th or 'без темы'}, источник «{src}», "
            f"состояние: {STATUS_TITLES.get(candidate.status, candidate.status.value)}"
        ]
        if not facts:
            lines.append(
                "Разбора нет: пост прошёл конвейер до того, как система начала записывать, "
                "из чего складывается решение."
            )
        else:
            origin = {
                "auto": "отобран порогом автоматически",
                "manual": "заказан вручную кнопкой (порог не применялся)",
                "batch": "из партии на день (порог не применялся)",
            }.get(str(facts.get("origin")), "происхождение не записано")
            lines.append(f"Как попал: {origin}")
            if facts.get("score") is not None:
                thr = facts.get("threshold")
                lines.append(
                    f"Заметность: {facts['score']}× медианы канала"
                    + (f" при пороге {thr}×" if thr is not None else " (порога не было)")
                )
            for key, label in [
                ("forwards", "Пересылок у исходника"),
                ("median_forwards", "Медиана канала"),
                ("trust_score", "Доверие источнику"),
                ("model", "Модель рерайта"),
                ("persona", "Персона"),
                ("rubric", "Подтема"),
                ("source_length", "Длина исходника"),
                ("result_length", "Длина результата"),
            ]:
                if facts.get(key) is not None:
                    lines.append(f"{label}: {facts[key]}")
            if facts.get("rubric_decided_by"):
                lines.append(
                    "Подтему решали по "
                    + ("исходнику, до рерайта" if facts["rubric_decided_by"] == "raw" else "готовому тексту")
                )
            if facts.get("edited_via"):
                lines.append(
                    f"Правка редактора: {facts.get('edit_length_before')} → "
                    f"{facts.get('edit_length_after')} знаков, "
                    + ("из бота" if facts["edited_via"] == "bot" else "из панели")
                )
            if facts.get("published_to"):
                lines.append("Вышел в: " + ", ".join(facts["published_to"]))
        return ToolResult(text="\n".join(lines), summary=f"разбор поста {post_code(candidate.id)}")

    async def _actions_log(self, args: dict) -> ToolResult:
        theme = await self._theme_by_name(args.get("theme"))
        days = self._days(args)
        limit = self._limit(args)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(AuditLog, Theme.name)
            .outerjoin(Theme, Theme.id == AuditLog.theme_id)
            .where(AuditLog.created_at >= since)
            .order_by(AuditLog.created_at.desc())
        )
        if theme:
            stmt = stmt.where(AuditLog.theme_id == theme.id)
        rows = (await self.session.execute(stmt.limit(limit))).all()
        if not rows:
            return ToolResult(
                text=f"За {days} дн. в журнале ничего нет.", summary=f"журнал за {days} дн. — пусто"
            )
        lines = []
        for log, th in rows:
            who = log.actor_admin_username or (
                f"telegram {log.actor_tg_user_id}" if log.actor_tg_user_id else "система"
            )
            extra = ", ".join(f"{k}={v}" for k, v in (log.payload or {}).items())
            lines.append(
                f"- {log.created_at:%d.%m %H:%M} · {who} · {log.action.value}"
                + (f" · {th}" if th else "")
                + (f" · {extra}" if extra else "")
            )
        return ToolResult(
            text="\n".join(lines), summary=f"журнал за {days} дн. — {len(rows)} записей"
        )
