"""Регрессия на петлю обратной связи в скоринге.

На проде она положила систему целиком: 5171 отклонённый кандидат подряд при
22 публикациях. Механизм — авто-отклонение по порогу штрафовало источник, а
trust_score умножает будущие скоры, так что источник загонял сам себя в пол и
больше никогда не мог из него выбраться. Тесты ниже фиксируют оба
предохранителя, чтобы петля не вернулась незаметно."""

import inspect

from core.services import scoring
from core.services.trust_score import MAX_TRUST_SCORE, MIN_TRUST_SCORE


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
    """trust_score — множитель к скору. Нижняя граница должна оставлять
    источнику реальный шанс пройти порог, иначе автоматика тихо отключает
    канал без ведома оператора."""
    # При множителе MIN_TRUST_SCORE посту нужно набрать столько медиан канала,
    # чтобы дотянуть до порога отбора.
    medians_needed = scoring.SELECTION_SCORE_THRESHOLD / MIN_TRUST_SCORE
    assert medians_needed <= 3.0, (
        f"на дне доверия посту нужно {medians_needed:.1f} медиан канала — это "
        "недостижимо, источник замолкает навсегда"
    )


def test_trust_bounds_sane():
    assert 0 < MIN_TRUST_SCORE < 1.0 < MAX_TRUST_SCORE
