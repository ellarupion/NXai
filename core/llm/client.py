"""Тонкая обёртка над LiteLLM — единственное место в проекте, знающее про
конкретного LLM-провайдера (адаптировано из NX core/llm/client.py).
RewriteService зависит от этого интерфейса, а не от litellm/anthropic напрямую.
"""

from dataclasses import dataclass

import litellm

from core.config import Settings, get_settings
from core.logging import get_logger

logger = get_logger(__name__)

REWRITE_MODEL = "anthropic/claude-sonnet-5"
# Дешёвая модель для массовых операций, где не нужно творческое качество:
# скоринг-эвристики на тексте, классификация темы кандидата и т.п.
CLASSIFICATION_MODEL = "anthropic/claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class CompletionResult:
    """Ответ модели и то, во что он обошёлся.

    Токены кэша выделены отдельно намеренно. Системный промпт уходит с пометкой
    кэширования, и при повторных вызовах читается из кэша за десятую долю цены, а
    первая запись стоит на четверть дороже входа. Сложи мы всё в input_tokens —
    расход темы, которая переписывает посты пачкой, оказался бы завышен в разы:
    там из десяти вызовов девять читают тот же промпт из кэша."""

    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        cache_system_prompt: bool = True,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Вызов LLM с опциональным prompt caching статичной части system_prompt
        (персона/стиль темы — общая часть между вызовами рерайта одной темы)."""
        system_block: dict = {"type": "text", "text": system_prompt}
        if cache_system_prompt:
            system_block["cache_control"] = {"type": "ephemeral"}

        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": [system_block]},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            api_key=self.settings.anthropic_api_key,
        )

        choice = response.choices[0].message.content or ""
        usage = response.usage
        # Провайдеры отдают разбивку кэша по-разному и не всегда — getattr со
        # значением по умолчанию вместо обращения по точке: отсутствие разбивки не
        # должно ронять вызов, оно означает лишь «кэш не применялся».
        details = getattr(usage, "prompt_tokens_details", None)
        cache_read = int(getattr(details, "cached_tokens", 0) or 0)
        cache_write = int(
            getattr(details, "cache_creation_tokens", 0)
            or getattr(usage, "cache_creation_input_tokens", 0)
            or 0
        )
        # prompt_tokens у Anthropic — это уже ТОЛЬКО некэшированный вход, поэтому
        # вычитать из него ничего не надо. Но у части провайдеров туда включено всё;
        # max(0, ...) страхует от отрицательного числа, которое иначе ушло бы в цену.
        billable_input = max(0, int(usage.prompt_tokens) - cache_read - cache_write)
        logger.info(
            "llm.completion",
            model=model,
            input_tokens=billable_input,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        return CompletionResult(
            text=choice,
            input_tokens=billable_input,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
