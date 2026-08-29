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
class ToolCall:
    """Просьба модели позвать инструмент. arguments — JSON строкой, как их отдал
    провайдер: разбирать их должен тот, кто знает схему конкретного инструмента,
    а клиент про инструменты ничего не знает и знать не должен."""

    id: str
    name: str
    arguments: str


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
    # Непусто, когда модель вместо ответа просит данные (см. LLMClient.chat).
    tool_calls: tuple[ToolCall, ...] = ()
    # Зачем нужен отдельно от tool_calls: "length" означает, что ответ оборвался на
    # полуслове по потолку токенов, и показывать его человеку как готовый нельзя.
    finish_reason: str = ""


def _usage_tokens(usage: object) -> tuple[int, int, int]:
    """Оплачиваемый вход, чтение кэша и запись кэша из ответа провайдера.

    Провайдеры отдают разбивку кэша по-разному и не всегда — getattr со значением по
    умолчанию вместо обращения по точке: отсутствие разбивки не должно ронять вызов,
    оно означает лишь «кэш не применялся»."""
    details = getattr(usage, "prompt_tokens_details", None)
    cache_read = int(getattr(details, "cached_tokens", 0) or 0)
    cache_write = int(
        getattr(details, "cache_creation_tokens", 0)
        or getattr(usage, "cache_creation_input_tokens", 0)
        or 0
    )
    # prompt_tokens у Anthropic — это уже ТОЛЬКО некэшированный вход, поэтому вычитать
    # из него ничего не надо. Но у части провайдеров туда включено всё; max(0, ...)
    # страхует от отрицательного числа, которое иначе ушло бы в цену.
    billable_input = max(0, int(getattr(usage, "prompt_tokens", 0)) - cache_read - cache_write)
    return billable_input, cache_read, cache_write


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
        billable_input, cache_read, cache_write = _usage_tokens(response.usage)
        usage = response.usage
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
            finish_reason=str(getattr(response.choices[0], "finish_reason", "") or ""),
        )

    async def chat(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict],
        cache_system_prompt: bool = True,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        """То же, но с историей переписки и с инструментами.

        Отдельный метод, а не параметр complete(): у одноходовых вызовов (рерайт,
        классификация подтемы) вся суть в одном user_prompt, и подмешивать туда список
        сообщений значило бы усложнять их подпись ради чужого сценария.

        Инструменты описываются в формате OpenAI — litellm сам переводит их в формат
        Anthropic. Клиент про их смысл ничего не знает: он лишь передаёт схемы и
        возвращает просьбы модели, а исполняет их вызывающий (core/services/assistant.py).
        """
        system_block: dict = {"type": "text", "text": system_prompt}
        if cache_system_prompt:
            system_block["cache_control"] = {"type": "ephemeral"}

        extra = {"tools": tools} if tools else {}
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "system", "content": [system_block]}, *messages],
            max_tokens=max_tokens,
            api_key=self.settings.anthropic_api_key,
            **extra,
        )

        message = response.choices[0].message
        tool_calls = tuple(
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments or "{}")
            for call in (getattr(message, "tool_calls", None) or [])
        )
        billable_input, cache_read, cache_write = _usage_tokens(response.usage)
        logger.info(
            "llm.chat",
            model=model,
            turns=len(messages),
            tool_calls=[c.name for c in tool_calls],
            input_tokens=billable_input,
            output_tokens=response.usage.completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        return CompletionResult(
            text=message.content or "",
            input_tokens=billable_input,
            output_tokens=response.usage.completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            tool_calls=tool_calls,
            finish_reason=str(getattr(response.choices[0], "finish_reason", "") or ""),
        )
