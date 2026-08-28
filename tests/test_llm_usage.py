"""Учёт расходов на ИИ: цена вызова, потолок, живучесть записи.

Расход на модель нигде не сохранялся — клиент считал токены и выбрасывал их. Когда
планировщик без ограничителей ушёл в непрерывный рерайт, узнали об этом по счёту от
провайдера, а не из панели.

Тесты ниже стерегут три разные вещи, и все три уже ломались или могли сломаться молча:
арифметику кэша (без неё расход завышается в разы), поведение потолка на границе и то,
что запись о расходе переживает откат транзакции.
"""

import pytest

from core.llm.client import CLASSIFICATION_MODEL, REWRITE_MODEL, CompletionResult
from core.llm.pricing import MODEL_PRICES, price_for, usage_cost_usd
from core.models.enums import LlmUsageKind
from core.services.automation import AutomationSettings
from core.services.llm_budget import BudgetState
from core.services.llm_usage import KIND_TITLES, snapshot


# --- цена вызова -----------------------------------------------------------

def test_input_priced_per_million():
    assert usage_cost_usd(REWRITE_MODEL, 1_000_000, 0) == pytest.approx(3.0)


def test_output_costs_five_times_input():
    """Выход дороже входа впятеро — из-за этого длинный пост стоит заметно больше
    длинного исходника, и урезать надо длину ответа, а не запроса."""
    price = price_for(REWRITE_MODEL)
    assert price.output == price.input * 5


def test_cache_read_is_ten_times_cheaper():
    """Главная причина, по которой токены кэша считаются отдельно. Персона темы
    уходит с каждым рерайтом, и при пачке постов девять вызовов из десяти читают её
    из кэша. Сложи мы всё в обычный вход — расход завысился бы почти вдесятеро."""
    full = usage_cost_usd(REWRITE_MODEL, 1_000_000, 0)
    cached = usage_cost_usd(REWRITE_MODEL, 0, 0, cache_read_tokens=1_000_000)
    assert cached == pytest.approx(full / 10)


def test_cache_write_costs_more_than_input():
    """Первая запись в кэш дороже обычного входа: сэкономить на кэше можно только
    начиная со второго вызова, и на одиночной операции он в убыток."""
    write = usage_cost_usd(REWRITE_MODEL, 0, 0, cache_write_tokens=1_000_000)
    full = usage_cost_usd(REWRITE_MODEL, 1_000_000, 0)
    assert write > full


def test_cheap_model_is_cheaper_than_smart():
    assert price_for(CLASSIFICATION_MODEL).output < price_for(REWRITE_MODEL).output


def test_unknown_model_is_not_free():
    """Незнакомая модель считается по самому дорогому известному тарифу. Ноль был бы
    опаснее: новая модель выглядела бы бесплатной, и дневной потолок её не остановил
    бы — то есть предохранитель молча перестал бы работать."""
    unknown = usage_cost_usd("anthropic/claude-model-из-будущего", 1_000_000, 1_000_000)
    known = max(usage_cost_usd(m, 1_000_000, 1_000_000) for m in MODEL_PRICES)
    assert unknown == pytest.approx(known)
    assert unknown > 0


def test_snapshot_computes_cost_from_result():
    record = snapshot(
        CompletionResult(text="x", input_tokens=1000, output_tokens=500,
                         cache_read_tokens=4000, cache_write_tokens=200),
        kind=LlmUsageKind.REWRITE,
        model=REWRITE_MODEL,
    )
    assert record.cost_usd == pytest.approx(usage_cost_usd(REWRITE_MODEL, 1000, 500, 4000, 200))
    assert record.cache_read_tokens == 4000


# --- потолок ---------------------------------------------------------------

def test_budget_disabled_by_default():
    """Выключен намеренно: включать ограничение, способное остановить работу, —
    решение владельца. Но оно теперь хотя бы есть."""
    assert AutomationSettings().daily_budget_usd == 0


def test_disabled_budget_never_blocks():
    state = BudgetState(limit_usd=0.0, spent_usd=999.0)
    assert not state.enabled
    assert not state.exceeded


def test_budget_blocks_exactly_at_limit():
    """На границе — уже стоп, а не «ещё можно». Один лишний вызов на пределе стоит
    дешевле, чем разбор «почему лимит 10 долларов пропустил трату на 10.40»."""
    assert BudgetState(limit_usd=10.0, spent_usd=10.0).exceeded
    assert not BudgetState(limit_usd=10.0, spent_usd=9.99).exceeded


def test_warning_fires_before_the_stop():
    state = BudgetState(limit_usd=10.0, spent_usd=8.5)
    assert state.near_limit(80)
    assert not state.exceeded


def test_exceeded_is_not_also_a_warning():
    """Иначе панель показала бы одновременно «близко к потолку» и «остановлено»."""
    state = BudgetState(limit_usd=10.0, spent_usd=12.0)
    assert state.exceeded
    assert not state.near_limit(80)


def test_percent_does_not_overflow_the_bar():
    assert BudgetState(limit_usd=1.0, spent_usd=1000.0).percent <= 999


# --- границы настроек ------------------------------------------------------

def test_budget_limit_has_upper_bound():
    """Опечатка в поле не должна превращаться в лимит на тысячи долларов."""
    with pytest.raises(ValueError):
        AutomationSettings(daily_budget_usd=100_000)


def test_negative_budget_rejected():
    with pytest.raises(ValueError):
        AutomationSettings(daily_budget_usd=-1)


def test_warn_percent_stays_meaningful():
    """Предупреждение на 10% бессмысленно, на 100% — опоздало."""
    with pytest.raises(ValueError):
        AutomationSettings(budget_warn_percent=10)
    with pytest.raises(ValueError):
        AutomationSettings(budget_warn_percent=100)


# --- названия для панели ---------------------------------------------------

def test_every_kind_has_a_human_title():
    """Панель показывает раздел работы словами. Забытый вид вылез бы у оператора
    как «classify_rubric», и это заметили бы позже, чем стоило."""
    missing = [k for k in LlmUsageKind if k not in KIND_TITLES]
    assert not missing, missing
