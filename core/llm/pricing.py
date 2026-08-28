"""Сколько стоит обращение к модели.

Клиент считал токены и выбрасывал их: ни таблицы, ни страницы, ни потолка не было, и
на вопрос «сколько ушло за вчера» ответить было нечем. Это уже стоило денег —
планировщик без ограничителей ушёл в непрерывный рерайт, и заметили это не по счётчику,
а по счёту от провайдера.

Здесь токены превращаются в деньги. Тарифы держим в коде, а не в настройках панели: их
меняет не оператор, а провайдер, и вслед за ним — разработчик. Цены за миллион токенов,
в долларах: счёт приходит в долларах, а придуманный курс рубля врал бы.

Про кэш важно понимать вот что. Системный промпт (персона темы) отправляется с пометкой
кэширования, поэтому при повторных вызовах он читается из кэша за десятую долю цены, а
первая запись в кэш стоит на четверть дороже обычного входа. Считать всё по цене входа
значило бы завышать расход в разы на теме, которая переписывает посты пачкой: там из
десяти вызовов девять читают тот же промпт из кэша.
"""

from dataclasses import dataclass

from core.llm.client import CLASSIFICATION_MODEL, REWRITE_MODEL


@dataclass(frozen=True)
class ModelPrice:
    """Цена за миллион токенов, в долларах."""

    input: float
    output: float
    # Запись в кэш — 1.25× от входа, чтение — 0.1× (тарифы Anthropic на 5-минутный кэш).
    cache_write: float
    cache_read: float


MODEL_PRICES: dict[str, ModelPrice] = {
    REWRITE_MODEL: ModelPrice(input=3.0, output=15.0, cache_write=3.75, cache_read=0.30),
    CLASSIFICATION_MODEL: ModelPrice(input=1.0, output=5.0, cache_write=1.25, cache_read=0.10),
}

# Человеческие названия для панели: «claude-sonnet-5» оператору ничего не говорит.
MODEL_TITLES: dict[str, str] = {
    REWRITE_MODEL: "Умная",
    CLASSIFICATION_MODEL: "Быстрая",
}

# Если провайдер добавит модель, а тариф забудут прописать, расход посчитается по самой
# дорогой из известных. Ноль был бы хуже: незнакомая модель выглядела бы бесплатной, и
# потолок расходов её бы не остановил.
_FALLBACK = max(MODEL_PRICES.values(), key=lambda p: p.output)


def price_for(model: str) -> ModelPrice:
    return MODEL_PRICES.get(model, _FALLBACK)


def model_title(model: str) -> str:
    return MODEL_TITLES.get(model, model)


def usage_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Стоимость одного вызова. input_tokens — только дорогая часть входа: токены,
    прочитанные из кэша и записанные в него, приходят отдельными числами и по своим
    тарифам."""
    price = price_for(model)
    return (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + cache_write_tokens * price.cache_write
    ) / 1_000_000
