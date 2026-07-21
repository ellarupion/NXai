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
