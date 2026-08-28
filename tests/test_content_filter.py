"""Отсев рекламы источников и постов без текста.

Оба случая пришли с прода. Пост-картинка без подписи давал LLM пустой промпт,
и та отвечала репликой «слышь, ты чего замолчал, дай текст» — эта реплика
уходила редактору как готовый пост. А реклама источника («интенсив, пиши в
личку @lis_martovskiy, 200 реакций — и выложу») исправно набирала пересылки,
проходила порог и переписывалась вместе с чужим ником и ценами.

Половина тестов ниже — про ЛОЖНЫЕ срабатывания: слишком жадный фильтр хуже
пропущенной рекламы, потому что молча съедает нормальный контент.
"""

from core.services.content_filter import (
    MIN_REWRITABLE_LENGTH,
    ad_signals,
    is_too_short_to_rewrite,
    looks_like_ad,
)


# --- посты без текста -------------------------------------------------------

def test_photo_without_caption_is_not_rewritable():
    assert is_too_short_to_rewrite("")
    assert is_too_short_to_rewrite("   \n  ")


def test_emoji_only_caption_is_not_rewritable():
    assert is_too_short_to_rewrite("🔥🔥🔥")


def test_normal_post_is_rewritable():
    text = (
        "Спать люблю один. Всегда. Но есть моменты, когда просыпаешься — "
        "а рядом человек, и это приятно."
    )
    assert len(text) > MIN_REWRITABLE_LENGTH
    assert not is_too_short_to_rewrite(text)


# --- реклама источника ------------------------------------------------------

def test_real_promo_post_from_production():
    """Дословный пост, из-за которого всё и началось (сокращён)."""
    text = (
        "Тема жирная, отзывы будут — заряжу подробный разбор.\n\n"
        "Условие простое: 200 реакций 🔥 — и пост выходит.\n\n"
        "P.S. Завтра стартует офлайн-интенсив в Новосибирске. "
        "Группа почти закрыта, но есть одно свободное место.\n\n"
        "Хочешь — пиши в личку: @lis_martovskiy. Кто не успел — сам виноват."
    )
    assert looks_like_ad(text), ad_signals(text)


def test_erid_marking_alone_is_enough():
    """Маркировка erid обязательна для рекламы в РФ — двух сигналов не нужно."""
    assert looks_like_ad("Отличный сервис для сна. erid: 2Vfnxy8ZQ1p")


def test_hashtag_reklama_alone_is_enough():
    assert looks_like_ad("Проверенный подрядчик по ремонту. #реклама")


def test_course_sale_detected():
    text = "Запись на курс открыта. Стоимость 15000 руб, промокод BRO на скидку."
    assert looks_like_ad(text), ad_signals(text)


# --- ложные срабатывания ----------------------------------------------------

def test_single_weak_signal_is_not_ad():
    """Слово «курс» в обычном рассуждении не делает пост рекламой."""
    text = (
        "Любой курс по саморазвитию обещает изменить жизнь за месяц. "
        "На деле меняет её привычка, которую держишь год. Разница в том, "
        "что привычку нельзя купить, а курс можно."
    )
    assert not looks_like_ad(text), ad_signals(text)


def test_price_mention_in_normal_post_is_not_ad():
    text = (
        "Сколько стоит завести собаку в первый год — честная смета без романтики. "
        "Прививки, корм, ветеринар: выходит заметно больше, чем кажется на старте."
    )
    assert not looks_like_ad(text), ad_signals(text)


def test_plain_advice_post_is_not_ad():
    text = (
        "Проверил на себе: 30 дней холодного душа. Сон стал глубже, а утро "
        "перестало быть борьбой — раскачка ушла с 40 минут до пяти. "
        "Не магия. Просто тело перестаёт торговаться."
    )
    assert not looks_like_ad(text), ad_signals(text)
    assert not is_too_short_to_rewrite(text)


def test_signals_are_reported_for_debugging():
    """Список сигналов должен быть читаемым: по нему разбирают ложные срабатывания."""
    signals = ad_signals("Пиши в личку @expert_guy, запись на интенсив открыта")
    assert signals
    assert all(isinstance(s, str) and s for s in signals)


# --- ограничители расхода на LLM ------------------------------------------

def test_rewrite_limits_cap_spending_for_any_allowed_setting():
    """Рерайт — единственная дорогая операция (умная модель на пост), и до появления
    лимитов джоб брал ВСЕХ отобранных кандидатов за тик. На проде это вылилось в
    непрерывный расход: порог отбора стал проходимым, и недели накопленных кандидатов
    ушли в модель одной пачкой.

    Теперь ограничители настраиваются из панели, поэтому сторожить надо не одно
    значение, а ГРАНИЦЫ: важно, что даже выкрутив их на максимум, оператор не получит
    неконтролируемый расход."""
    import scheduler
    from core.services.automation import AutomationSettings

    field = AutomationSettings.model_fields["rewrite_batch_limit"]
    worst_batch = next(m.le for m in field.metadata if hasattr(m, "le"))
    per_hour = worst_batch * (60 // scheduler.DEDUP_REWRITE_INTERVAL_MINUTES)
    assert per_hour <= 700, f"{per_hour} рерайтов в час — это неконтролируемый расход"

    stock_field = AutomationSettings.model_fields["rewrite_stock_days"]
    worst_stock = next(m.le for m in stock_field.metadata if hasattr(m, "le"))
    assert worst_stock <= 7, "запас больше недели — платим за то, что протухнет"


def test_rewrite_limits_defaults_are_conservative():
    """Значения по умолчанию должны быть заметно мягче предельных: система из коробки
    не обязана позволять максимум, который допускает форма."""
    from core.services.automation import AutomationSettings

    defaults = AutomationSettings()
    assert defaults.rewrite_batch_limit <= 10
    assert defaults.rewrite_stock_days <= 3
    assert defaults.min_rewrite_stock >= 1


def test_stock_cannot_be_set_above_what_theme_can_publish():
    """Запас больше, чем тема успеет опубликовать за отведённые дни, — это оплаченные
    посты в стол. Каждое значение по отдельности в границах, поймать можно только
    парной проверкой."""
    import pytest

    from core.services.automation import AutomationSettings

    with pytest.raises(ValueError):
        AutomationSettings(min_rewrite_stock=50, max_daily_batch=1, rewrite_stock_days=1)
