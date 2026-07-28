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

def test_rewrite_has_batch_and_stock_limits():
    """Рерайт — единственная дорогая операция (Sonnet на пост), и до этого
    джоб брал ВСЕХ SELECTED-кандидатов за тик без ограничений. На проде это
    вылилось в непрерывный расход: порог отбора стал проходимым, и недели
    накопленных кандидатов ушли в LLM одной пачкой.

    Тест сторожит оба потолка — скорости и смысла."""
    import scheduler

    assert scheduler.REWRITE_BATCH_LIMIT > 0
    # Потолок скорости: сколько постов максимум уйдёт в LLM за час.
    per_hour = scheduler.REWRITE_BATCH_LIMIT * (60 // scheduler.DEDUP_REWRITE_INTERVAL_MINUTES)
    assert per_hour <= 120, f"{per_hour} рерайтов в час — это неконтролируемый расход"
    # Потолок смысла: запас готовых постов не должен превышать нескольких дней
    # публикации, иначе платим за то, что протухнет в статусе REWRITTEN.
    assert scheduler.REWRITE_STOCK_DAYS <= 3
    assert scheduler.MIN_REWRITE_STOCK >= 1
