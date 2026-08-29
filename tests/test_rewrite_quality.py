"""Замер качества рерайта: перестановка, разбор приговора и итог словами.

Про качество текстов в системе не было ни одного числа: поменяли персону — судили по
ощущению от последних просмотренных постов. Замер отвечает числом, и именно поэтому
его собственная арифметика должна быть безупречной: неверный перевод «победил первый»
в «победила новая персона» даёт не ошибку, а уверенный вывод наоборот, и заметить это
по результату невозможно.

Здесь чистые функции — их можно проверить без базы и без модели. Сам прогон (десятки
обращений к модели, коммит после каждой пары) проверен на живой базе с подставной
моделью.
"""

import pytest

from core.models.enums import QualityVerdict
from core.services.rewrite_quality import (
    MIN_SIZE,
    _is_refusal,
    _to_verdict,
    parse_judgement,
    resolve_pair,
    verdict_summary,
)


class FakeRun:
    def __init__(self, baseline, variant, ties):
        self.wins_baseline = baseline
        self.wins_variant = variant
        self.ties = ties


# --- перевод позиции в вариант ----------------------------------------------


def test_first_wins_when_baseline_shown_first():
    assert _to_verdict("first", first_is_baseline=True) is QualityVerdict.BASELINE


def test_first_wins_when_variant_shown_first():
    """Тот же приговор судьи означает противоположное, если варианты переставили.
    Здесь легче всего ошибиться, и ошибка дала бы уверенный вывод наоборот."""
    assert _to_verdict("first", first_is_baseline=False) is QualityVerdict.VARIANT


def test_second_wins_both_ways():
    assert _to_verdict("second", first_is_baseline=True) is QualityVerdict.VARIANT
    assert _to_verdict("second", first_is_baseline=False) is QualityVerdict.BASELINE


def test_tie_stays_tie_regardless_of_order():
    assert _to_verdict("tie", first_is_baseline=True) is QualityVerdict.TIE
    assert _to_verdict("tie", first_is_baseline=False) is QualityVerdict.TIE


# --- двойное судейство ------------------------------------------------------


def test_agreeing_judgements_give_a_winner():
    assert (
        resolve_pair(QualityVerdict.VARIANT, QualityVerdict.VARIANT) is QualityVerdict.VARIANT
    )
    assert (
        resolve_pair(QualityVerdict.BASELINE, QualityVerdict.BASELINE) is QualityVerdict.BASELINE
    )


def test_disagreeing_judgements_give_a_tie():
    """Судья поменял мнение от одной перестановки — значит, разница между текстами
    меньше влияния их порядка. Засчитать победу здесь значит выдать шум за результат."""
    assert resolve_pair(QualityVerdict.VARIANT, QualityVerdict.BASELINE) is QualityVerdict.TIE
    assert resolve_pair(QualityVerdict.BASELINE, QualityVerdict.VARIANT) is QualityVerdict.TIE


def test_one_sided_tie_is_a_tie():
    assert resolve_pair(QualityVerdict.VARIANT, QualityVerdict.TIE) is QualityVerdict.TIE


def test_position_bias_alone_never_produces_a_winner():
    """Судья, который всегда выбирает показанный первым, не должен дать победителя
    ни в одной паре — ради этого двойное судейство и заведено."""
    for baseline_first in (True, False):
        direct = _to_verdict("first", first_is_baseline=baseline_first)
        swapped = _to_verdict("first", first_is_baseline=not baseline_first)
        assert resolve_pair(direct, swapped) is QualityVerdict.TIE


def test_a_genuinely_better_variant_wins_both_ways():
    """А судья, который в обоих проходах выбирает один и тот же текст, даёт победу —
    иначе замер не смог бы обнаружить вообще ничего."""
    for baseline_first in (True, False):
        # «Новый» показан вторым в прямом проходе и первым в перевёрнутом.
        direct = _to_verdict("second" if baseline_first else "first", first_is_baseline=baseline_first)
        swapped = _to_verdict(
            "first" if baseline_first else "second", first_is_baseline=not baseline_first
        )
        assert resolve_pair(direct, swapped) is QualityVerdict.VARIANT


# --- разбор ответа судьи ----------------------------------------------------


def test_parses_the_expected_form():
    j = parse_judgement("ПОБЕДИТЕЛЬ: 2\nПОЧЕМУ: живее и короче")
    assert j.winner == "second"
    assert j.reason == "живее и короче"


def test_parses_tie():
    assert parse_judgement("ПОБЕДИТЕЛЬ: НИЧЬЯ\nПОЧЕМУ: одинаковые").winner == "tie"


def test_unparseable_answer_is_a_tie_not_a_guess():
    """Судья иногда отвечает рассуждением вместо формы. Засчитать победу по первому
    попавшемуся в тексте числу значило бы подмешать в замер случайность."""
    j = parse_judgement("Оба варианта неплохие, в первом 2 абзаца, но всё же трудно сказать.")
    assert j.winner == "tie"


def test_reason_is_trimmed_and_bounded():
    j = parse_judgement("ПОБЕДИТЕЛЬ: 1\nПОЧЕМУ: " + "очень длинно " * 100)
    assert len(j.reason) <= 300


def test_empty_answer_is_a_tie():
    assert parse_judgement("").winner == "tie"


# --- отказ модели переписывать ----------------------------------------------


def test_refusal_is_detected():
    """Пару, где переписывать было нечего, судить нельзя: победит тот, кто хоть что-то
    написал, а это оценка везения с исходником, а не качества персоны."""
    assert _is_refusal("NO_CONTENT")
    assert _is_refusal("  ")
    assert not _is_refusal("Нормальный переписанный текст.")


# --- итог словами -----------------------------------------------------------


def test_summary_names_the_winner():
    assert "Новый вариант лучше" in verdict_summary(FakeRun(2, 9, 1))
    assert "Текущий вариант лучше" in verdict_summary(FakeRun(9, 2, 1))


def test_summary_counts_ties_in_the_denominator():
    """«Выиграл в 9 из 12» честнее, чем «в 9 из 11, а про ничьи умолчим»."""
    assert "из 12" in verdict_summary(FakeRun(2, 9, 1))


def test_summary_refuses_to_call_a_winner_on_too_few_decided():
    """«2 против 1» читалось бы как победа, хотя это подбрасывание монеты."""
    text = verdict_summary(FakeRun(1, 2, 9))
    assert "Разницы не видно" in text


def test_summary_reports_a_draw():
    assert "поровну" in verdict_summary(FakeRun(5, 5, 2))


def test_summary_survives_an_empty_run():
    assert verdict_summary(FakeRun(0, 0, 0))


@pytest.mark.parametrize("decided", range(MIN_SIZE, MIN_SIZE + 3))
def test_summary_calls_a_winner_once_enough_pairs_are_decided(decided):
    assert "лучше" in verdict_summary(FakeRun(0, decided, 1))
