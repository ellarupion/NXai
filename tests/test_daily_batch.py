"""Отбор партии на день: разброс по подтемам и перемешивание.

Жалоба оператора была двойной. Во-первых, тема готовила посты непрерывно —
десятки в сутки, все в «Проверку», каждый за деньги. Во-вторых, «топ-N по
виральности» на практике оказывались N постами про одно и то же: источники в
один день пишут об общем инфоповоде, и залетает у всех одно.

Здесь тесты на отбор — чистая функция, её можно проверить без базы. Арифметику
долга (заказали 5, одобрили 3, отклонили 1 → доедет один) проверяет
verify-скрипт на живой базе: она вся про запросы к БД, и мокать их значило бы
тестировать моки.
"""

import random
from types import SimpleNamespace

from core.services.force_generate import _round_robin_by_rubric


def post(rubric, score):
    return SimpleNamespace(rubric=rubric, score=score, id=f"{rubric}-{score}")


def rubrics_of(picked):
    return [p.rubric for p in picked]


def test_top_by_virality_alone_would_be_all_one_rubric():
    """Исходная ситуация: самые виральные посты дня — все про деньги."""
    pool = [post("деньги", 9.0 - i) for i in range(5)] + [post("отношения", 1.0)]
    by_score = sorted(pool, key=lambda c: c.score, reverse=True)[:5]
    assert set(rubrics_of(by_score)) == {"деньги"}


def test_round_robin_spreads_across_rubrics():
    """Тот же пул через отбор: подтемы чередуются, менее виральный пост другой
    подтемы вытесняет пятый пост про деньги."""
    pool = [post("деньги", 9.0 - i) for i in range(5)] + [post("отношения", 1.0)]
    picked = _round_robin_by_rubric(pool, 5)
    assert len(picked) == 5
    assert "отношения" in rubrics_of(picked)


def test_best_of_each_rubric_wins_inside_its_bucket():
    """Внутри подтемы порядок по виральности — берём лучшее, а не случайное."""
    pool = [post("деньги", 1.0), post("деньги", 9.0), post("отношения", 2.0)]
    picked = _round_robin_by_rubric(pool, 2)
    money = [p for p in picked if p.rubric == "деньги"]
    assert money and money[0].score == 9.0


def test_order_is_shuffled_not_grouped_by_rubric():
    """Без перемешивания партия приходит блоками «пять про деньги, пять про
    отношения», и оператор разбирает её ровно с тем ощущением зацикленности,
    от которого уходим."""
    pool = [post(f"тема{i % 4}", 10.0 - i) for i in range(20)]
    random.seed(7)
    grouped = 0
    for _ in range(20):
        picked = rubrics_of(_round_robin_by_rubric(list(pool), 8))
        # Идеальный круг «1,2,3,4,1,2,3,4» — признак того, что шафл не работал.
        if picked == picked[:4] * 2:
            grouped += 1
    assert grouped == 0


def test_single_rubric_pool_still_fills_the_order():
    """Разброс — предпочтение, а не условие: если вся ниша сегодня об одном,
    партия всё равно собирается. Пустая «Проверка» хуже однообразной."""
    pool = [post("деньги", 5.0 - i * 0.1) for i in range(10)]
    assert len(_round_robin_by_rubric(pool, 5)) == 5


def test_unclassified_posts_participate():
    """Пост без подтемы (классификатор промолчал) — своя корзина, а не отвал."""
    pool = [post("деньги", 9.0), post(None, 8.0), post("деньги", 7.0)]
    picked = _round_robin_by_rubric(pool, 2)
    assert None in rubrics_of(picked)


def test_pool_smaller_than_order_returns_everything():
    pool = [post("деньги", 3.0), post("отношения", 2.0)]
    assert len(_round_robin_by_rubric(pool, 10)) == 2


def test_order_size_is_respected():
    pool = [post(f"тема{i % 3}", float(i)) for i in range(30)]
    assert len(_round_robin_by_rubric(pool, 4)) == 4


def test_batch_cap_protects_the_human_not_the_wallet():
    """Потолок партии — про то, сколько карточек человек разберёт за раз.
    Деньги стережёт лимит планировщика, это отдельный предохранитель."""
    from core.services.daily_batch import MAX_DAILY_BATCH

    assert 5 <= MAX_DAILY_BATCH <= 25
