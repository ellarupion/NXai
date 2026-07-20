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
    text: str
    input_tokens: int
    output_tokens: int


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
        logger.info(
            "llm.completion",
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
        return CompletionResult(
            text=choice,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
