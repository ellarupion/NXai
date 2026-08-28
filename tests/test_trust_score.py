"""Регрессия на петлю обратной связи в скоринге.

На проде она положила систему целиком: 5171 отклонённый кандидат подряд при
22 публикациях. Механизм — авто-отклонение по порогу штрафовало источник, а
trust_score умножает будущие скоры, так что источник загонял сам себя в пол и
больше никогда не мог из него выбраться. Тесты ниже фиксируют оба
предохранителя, чтобы петля не вернулась незаметно."""

import inspect

import pytest

from core.services import scoring
from core.services.automation import AutomationSettings


def test_auto_reject_does_not_penalize_source():
    """Не пройти порог виральности — штатный исход для БОЛЬШИНСТВА постов:
    порог нормирован по медиане канала, и половина его постов ниже медианы по
    определению. Штраф за это означал бы наказание источника за нормальную
    статистику."""
    source = inspect.getsource(scoring.ScoringService.reject_if_matured)
    assert "adjust_trust_score(self.session" not in source, (
        "reject_if_matured снова штрафует источник — это замыкает скоринг сам "
        "на себя: отклонили -> доверие вниз -> скоры ниже -> отклонили ещё"
    )


def test_trust_floor_cannot_silently_disable_source():
    """trust_score — множитель к скору. Нижняя граница должна оставлять источнику
    реальный шанс пройти порог, иначе автоматика тихо отключает канал без ведома
    оператора."""
    defaults = AutomationSettings()
    medians_needed = defaults.selection_score_threshold / defaults.min_trust_score
    assert medians_needed <= 3.0, (
        f"на дне доверия посту нужно {medians_needed:.1f} медиан канала — это "
        "недостижимо, источник замолкает навсегда"
    )


def test_operator_cannot_recreate_the_death_spiral_from_settings():
    """Пороги теперь настраиваются из панели — значит въехать в ту же яму можно уже
    руками, а не только петлёй. Пара «высокий порог + низкое дно доверия» должна
    отвергаться при сохранении, а не выясняться через неделю тишины в канале."""
    with pytest.raises(ValueError):
        AutomationSettings(selection_score_threshold=10, min_trust_score=0.1)


def test_trust_bounds_must_leave_room_to_move():
    """Нижняя граница выше верхней означала бы, что вес источника не меняется вовсе,
    то есть весь механизм доверия молча выключен."""
    with pytest.raises(ValueError):
        AutomationSettings(min_trust_score=1.0, max_trust_score=1.0)


def test_trust_events_have_the_right_signs():
    """Раньше знак штрафа выбирал вызывающий, и три места писали минус, а одно плюс.
    Перепутанный знак означал бы, что система поощряет источник за отклонения, и
    поймать это было нечем."""
    from core.services.trust_score import TrustEvent, _delta_for

    defaults = AutomationSettings()
    assert _delta_for(TrustEvent.REJECTED, defaults) < 0
    assert _delta_for(TrustEvent.DUPLICATE, defaults) < 0
    assert _delta_for(TrustEvent.SUCCESS, defaults) > 0
    # Ручное отклонение — более сильный сигнал, чем повтор чужой новости.
    assert _delta_for(TrustEvent.REJECTED, defaults) < _delta_for(TrustEvent.DUPLICATE, defaults)
