"""Паспорт поста: что именно считается честным ответом на «почему такой пост».

Разбор собирается из четырёх стадий, каждая в своё время и в своей транзакции.
Смысл живёт в сборщиках фактов — они чистые, и проверяются здесь. Накопление
стадий в JSONB и то, что паспорт уходит вместе с постом, проверено на живой базе:
это целиком про запросы, и мокать их значило бы тестировать моки.

Главное, что стерегут тесты ниже, — ложь в справке. Панель рисует по паспорту
фразы вида «обогнал канал в 2,4 раза при пороге 1,8», и если у поста, заказанного
кнопкой, в паспорте окажется действующий порог, панель нарисует сравнение,
которого никто не делал.
"""

from core.services.post_passport import (
    edit_facts,
    persona_summary,
    publish_facts,
    rewrite_facts,
    rubric_facts,
    selection_facts,
)


def test_manual_post_has_no_threshold():
    """Порога у ручного заказа не было. None здесь — не «не знаем», а «не применялся»."""
    facts = selection_facts(origin="manual", score=0.4, threshold=None)
    assert facts["origin"] == "manual"
    assert facts["threshold"] is None


def test_auto_post_keeps_threshold_next_to_score():
    """Скор без порога нечитаем: 2.4 — это много или мало, зависит от порога."""
    facts = selection_facts(origin="auto", score=2.4, threshold=1.8)
    assert facts["score"] == 2.4
    assert facts["threshold"] == 1.8


def test_numbers_are_rounded_for_reading():
    """В справке человеку, а не в отчёте: 2.4123456789× медианы читать невозможно."""
    facts = selection_facts(
        origin="auto", score=2.4123456789, threshold=1.79999, median_forwards=49.4999,
        trust_score=1.2345678,
    )
    assert facts["score"] == 2.412
    assert facts["threshold"] == 1.8
    assert facts["median_forwards"] == 49.5
    assert facts["trust_score"] == 1.235


def test_missing_numbers_stay_none_not_zero():
    """Ноль пересылок и «неизвестно сколько» — разные вещи, и панель показывает
    их по-разному. Округление не должно превращать второе в первое."""
    facts = selection_facts(origin="auto", score=None, threshold=None)
    assert facts["score"] is None
    assert facts["median_forwards"] is None
    assert facts["trust_score"] is None


def test_rubric_remembers_what_it_was_decided_by():
    """Подтему определяют либо по исходнику (партия на день — до оплаты рерайта),
    либо по готовому тексту. Во втором случае классификатор видел то же, что
    увидит читатель, и доверие к метке разное."""
    assert rubric_facts(rubric="Финансы", decided_by="raw")["rubric_decided_by"] == "raw"
    assert rubric_facts(rubric="Финансы", decided_by="rewritten")["rubric_decided_by"] == "rewritten"


def test_persona_summary_collapses_and_truncates():
    """Промпт персоны бывает на страницу; в справке важно, чем писали, а не весь текст."""
    summary = persona_summary("  Пиши   коротко\n\nи без канцелярита. " * 40)
    assert len(summary) <= 201
    assert summary.endswith("…")
    assert "  " not in summary


def test_persona_summary_survives_empty_prompt():
    """Персона может быть не задана — в справке это должно быть сказано словами,
    а не пустой строкой, которая выглядит как потерянные данные."""
    assert rewrite_facts(
        model="m", persona_summary=persona_summary(""), source_length=1,
        result_length=1, variant_no=1,
    )["persona"] == "персона не задана"


def test_short_persona_is_not_truncated():
    assert persona_summary("Пиши коротко.") == "Пиши коротко."


def test_stages_do_not_share_keys():
    """Стадии дописываются в один словарь по мере прохождения. Совпади ключ у
    двух стадий — поздняя молча затёрла бы раннюю, и разбор соврал бы, не
    сломавшись: в справке осталось бы правдоподобное, но чужое число."""
    stages = [
        selection_facts(origin="auto", score=1.0, threshold=1.0),
        rewrite_facts(
            model="m", persona_summary="п", source_length=1, result_length=1, variant_no=1
        ),
        rubric_facts(rubric="Финансы", decided_by="rewritten"),
        edit_facts(via="panel", length_before=1, length_after=1),
        publish_facts(channels=["К"], with_photo=False),
    ]
    seen: set[str] = set()
    for stage in stages:
        overlap = seen & set(stage)
        assert not overlap, f"стадии делят ключи: {overlap}"
        seen |= set(stage)


def test_edit_facts_record_both_lengths():
    """Обе длины, а не разница: «было 310, стало 288» отвечает на вопрос
    «сильно ли правили», а «-22» без исходной длины — нет."""
    facts = edit_facts(via="bot", length_before=310, length_after=288)
    assert facts["edit_length_before"] == 310
    assert facts["edit_length_after"] == 288
    assert facts["edited_via"] == "bot"


def test_publish_facts_keep_channel_titles_not_ids():
    """Названия, а не идентификаторы: справку читает человек, и «Канал А» он
    узнаёт, а UUID канала — нет."""
    facts = publish_facts(channels=["Канал А", "Канал Б"], with_photo=True)
    assert facts["published_to"] == ["Канал А", "Канал Б"]
    assert facts["published_with_photo"] is True
