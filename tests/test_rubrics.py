"""Подтемы: чередование выдачи и чистка списка рубрик.

Жалоба, из-за которой это появилось: канал «зацикливается» — подряд идут посты
про одно и то же. Причина не случайна. Источники в один день пишут об одном
инфоповоде, а отбор по виральности перекос усиливает, потому что залетевшее в
нише залетает сразу у всех. Балансировка даёт планировщику вторую ось.

Тесты ниже сторожат ровно те свойства, потерять которые легко и незаметно:
подмешивание случайности, живучесть при перекошенном запасе и то, что новая
разметка не морозит старые посты.
"""

from types import SimpleNamespace

import pytest

from core.services.rubrics import _parse_list, freshest_by_rubric


def post(rubric, score=1.0):
    return SimpleNamespace(rubric=rubric, score=score)


# --- чередование -----------------------------------------------------------

def test_prefers_rubric_that_has_not_been_out():
    money, love = post("деньги"), post("отношения")
    assert freshest_by_rubric([money, love], ["деньги", "деньги"]) == [love]


def test_least_recent_wins_not_merely_absent_from_last_slot():
    """Правило — «дольше всех не выходила», а не «не была последней».

    Разница видна на трёх рубриках: если смотреть только на последний пост,
    «здоровье» и «отношения» выглядят одинаково допустимыми, хотя отношения
    выходили через один, а здоровье — три поста назад."""
    love, health = post("отношения"), post("здоровье")
    recent = ["деньги", "отношения", "деньги", "здоровье"]
    assert freshest_by_rubric([love, health], recent) == [health]


def test_returns_all_ties_so_caller_keeps_the_dice():
    """Возвращается подмножество, а не победитель.

    Это не мелочь реализации: выбор внутри темы взвешенно-случайный по скору
    (SchedulerPoolService), и если сузить до одного поста, канал начнёт крутить
    строго лучший по скору пост каждой рубрики по кругу — предсказуемо и скучно."""
    a, b = post("карьера", score=5.0), post("карьера", score=0.2)
    picked = freshest_by_rubric([a, b], ["деньги", "отношения"])
    assert picked == [a, b]


# --- живучесть -------------------------------------------------------------

def test_single_rubric_stock_still_publishes():
    """Пустая очередь хуже перекоса: если весь запас одной рубрики, выходит
    пост этой рубрики, а не тишина."""
    only = [post("деньги"), post("деньги")]
    assert freshest_by_rubric(only, ["деньги", "деньги", "деньги"]) == only


def test_no_history_returns_everything():
    stock = [post("деньги"), post(None)]
    assert freshest_by_rubric(stock, []) == stock


def test_empty_stock_stays_empty():
    assert freshest_by_rubric([], ["деньги"]) == []


def test_unclassified_posts_are_not_starved():
    """Момент включения рубрик — узкое место: весь накопленный запас без
    рубрики, свежее уже размечено. Если считать неразмеченное «недавно
    выходившим», старые посты не выйдут никогда."""
    old, fresh = post(None), post("деньги")
    assert freshest_by_rubric([old, fresh], ["деньги", "деньги"]) == [old]


def test_renamed_rubric_does_not_freeze_old_posts():
    """Рубрики хранятся строкой, а не FK: оператор переименовал «деньги» в
    «финансы», и у старых постов осталось прежнее значение. Оно просто
    перестаёт совпадать с историей — то есть считается максимально давним,
    и такой пост выйдет, а не залипнет."""
    stale = post("деньги")
    current = post("финансы")
    assert freshest_by_rubric([stale, current], ["финансы", "финансы"]) == [stale]


# --- разбор ответа модели --------------------------------------------------

def test_parses_plain_json_array():
    assert _parse_list('["деньги", "отношения"]') == ["деньги", "отношения"]


def test_parses_json_wrapped_in_markdown_fence():
    """Модель регулярно оборачивает ответ в ```json вопреки просьбе."""
    assert _parse_list('```json\n["деньги", "здоровье"]\n```') == ["деньги", "здоровье"]


def test_falls_back_to_lines_when_not_json():
    parsed = _parse_list("- деньги\n- отношения\n- здоровье")
    assert parsed == ["деньги", "отношения", "здоровье"]


# --- чистка списка от оператора --------------------------------------------

def test_clean_rubrics_drops_case_duplicates():
    """«Деньги» и «деньги» классификатор считает одной рубрикой, а баланс —
    двумя: половина постов ушла бы в одну, половина в другую, и чередование
    сломалось бы тихо."""
    from interfaces.api.routers.themes import _clean_rubrics

    assert _clean_rubrics(["Деньги", "деньги", " ДЕНЬГИ "]) == ["Деньги"]


def test_clean_rubrics_normalizes_whitespace_and_drops_empty():
    from interfaces.api.routers.themes import _clean_rubrics

    assert _clean_rubrics(["  личные   финансы ", "", "   "]) == ["личные финансы"]


def test_clean_rubrics_rejects_oversized_list():
    from fastapi import HTTPException

    from core.services.rubrics import MAX_RUBRICS
    from interfaces.api.routers.themes import _clean_rubrics

    with pytest.raises(HTTPException) as exc:
        _clean_rubrics([f"тема{i}" for i in range(MAX_RUBRICS + 1)])
    assert exc.value.status_code == 400
