"""StyleExtractor (аудит, п.7.2): по 10–30 референс-постам канала LLM
описывает его «голос» — тон, длину, форматирование, характерные обороты — и
возвращает готовый persona-промпт. Снимает главный порог входа: оператору не
нужно вручную писать промпт-персону, достаточно показать примеры постов.

Возвращает текст-описание; сохранять его в ChannelBot.persona_prompt или нет
решает оператор в панели (предлагаем, не применяем молча)."""

from core.llm.client import REWRITE_MODEL, LLMClient
from core.logging import get_logger

logger = get_logger(__name__)

MIN_REFERENCE_POSTS = 3
MAX_REFERENCE_POSTS = 50

_SYSTEM_PROMPT = """\
Ты — редактор, который формализует стиль Telegram-канала для последующей
генерации постов в том же голосе. Тебе дают несколько реальных постов канала.
Опиши его стиль как инструкцию для автора (персону), НЕ пересказывая сами
посты. Отрази: тон и обращение к читателю, типичную длину, форматирование и
эмодзи, характерные обороты и лексику, чего автор избегает. Ответь только
текстом персоны, 3–6 предложений, во втором лице («Пиши…»)."""

# Структурный вариант — для предзаполнения конструктора персоны в панели
# (core/services/persona.py). LLM обязан ответить строгим JSON; при сбое
# парсинга панель откатывается на текстовый вариант через поле custom.
_STRUCTURED_SYSTEM_PROMPT = """\
Ты — редактор, который формализует стиль Telegram-канала. Тебе дают несколько
реальных постов канала. Верни ТОЛЬКО валидный JSON без пояснений и без
markdown-ограждений, ровно с такими ключами:
{
  "tone_custom": "описание тона и голоса автора, 1-3 предложения, во втором лице («Пиши…»)",
  "length": "shorter" | "same" | "longer"  — типичная длина постов относительно среднего телеграм-поста (короткие/средние/длинные),
  "emoji": "none" | "few" | "many",
  "address": "ty" | "vy" | "neutral"  — как автор обращается к читателю,
  "custom": "остальные важные особенности стиля: характерные обороты, форматирование, чего автор избегает — 1-3 предложения"
}"""


def _parse_structured(raw: str) -> dict:
    """Достаёт JSON из ответа LLM (терпимо к ```-ограждениям). Возвращает
    только известные конструктору ключи с провалидированными значениями."""
    import json
    import re

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not a dict")

    result: dict = {}
    tone_custom = str(data.get("tone_custom") or "").strip()
    if tone_custom:
        result["tone"] = "custom"
        result["tone_custom"] = tone_custom
    if data.get("length") in ("shorter", "same", "longer"):
        result["length"] = data["length"]
    if data.get("emoji") in ("none", "few", "many"):
        result["emoji"] = data["emoji"]
    if data.get("address") in ("ty", "vy", "neutral"):
        result["address"] = data["address"]
    custom = str(data.get("custom") or "").strip()
    if custom:
        result["custom"] = custom
    if not result:
        raise ValueError("empty structured result")
    return result


class StyleExtractorError(Exception):
    """Текст уходит в HTTP-ответ панели как есть."""


async def extract_style(llm: LLMClient, reference_posts: list[str]) -> str:
    posts = [p.strip() for p in reference_posts if p and p.strip()]
    if len(posts) < MIN_REFERENCE_POSTS:
        raise StyleExtractorError(
            f"Нужно хотя бы {MIN_REFERENCE_POSTS} примера постов, чтобы выучить стиль"
        )
    posts = posts[:MAX_REFERENCE_POSTS]

    user_prompt = "\n\n---\n\n".join(posts)
    completion = await llm.complete(
        model=REWRITE_MODEL, system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt
    )
    logger.info("style_extractor.done", posts=len(posts))
    return completion.text.strip()


async def extract_style_structured(llm: LLMClient, reference_posts: list[str]) -> dict:
    """Структурный вариант extract_style: возвращает частичный persona_config
    для предзаполнения конструктора. При непарсибельном ответе LLM падает в
    текстовый режим: весь ответ кладётся в custom."""
    posts = [p.strip() for p in reference_posts if p and p.strip()]
    if len(posts) < MIN_REFERENCE_POSTS:
        raise StyleExtractorError(
            f"Нужно хотя бы {MIN_REFERENCE_POSTS} примера постов, чтобы выучить стиль"
        )
    posts = posts[:MAX_REFERENCE_POSTS]

    user_prompt = "\n\n---\n\n".join(posts)
    completion = await llm.complete(
        model=REWRITE_MODEL, system_prompt=_STRUCTURED_SYSTEM_PROMPT, user_prompt=user_prompt
    )
    try:
        result = _parse_structured(completion.text)
        logger.info("style_extractor.structured_done", posts=len(posts))
        return result
    except Exception:
        logger.warning("style_extractor.structured_parse_failed")
        return {"custom": completion.text.strip()}
