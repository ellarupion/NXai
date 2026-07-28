"""Markdown от LLM → HTML для Telegram.

Пришло с прода: карточка редактора показывала «_Осознанность_» с
подчёркиваниями. Она слалась вообще без parse_mode, тогда как публикация шла
с parse_mode=Markdown — редактор одобрял одно, в канал уходило другое.

Половина тестов ниже — про НЕразметку: текст, где «*» и «_» просто символы.
Жадный конвертер тут опаснее пропущенного курсива, потому что молча съедает
куски живого текста или, хуже, отдаёт Telegram HTML, который тот не разберёт.
"""

import re

from core.services.tg_format import escape, to_telegram_html

# Теги, которые Telegram понимает в parse_mode=HTML. Всё, что конвертер может
# выдать, обязано быть в этом списке.
ALLOWED = {"b", "i", "u", "s", "a", "code", "pre"}
_TAG = re.compile(r"</?([a-zA-Z]+)")


def tags(html: str) -> set[str]:
    return {m.lower() for m in _TAG.findall(html)}


# --- разметка ---------------------------------------------------------------

def test_italic_underscore_is_the_reported_case():
    """Дословно то, что увидел оператор в карточке."""
    assert to_telegram_html("_Осознанность_ — способность") == "<i>Осознанность</i> — способность"


def test_single_star_is_bold_as_the_prompt_promises():
    """Промпт рерайта просит телеграмный Markdown, где «*x*» — жирный
    (core/services/rewrite.py). Стандартный Markdown понимает это как курсив,
    но канал ждёт того, что заказано в промпте."""
    assert to_telegram_html("*жирный*") == "<b>жирный</b>"


def test_double_star_is_bold_too():
    """Модели по привычке пишут стандартный «**x**» вопреки промпту. В старом
    Markdown-режиме это рендерилось мусором со звёздочками."""
    assert to_telegram_html("**жирный**") == "<b>жирный</b>"


def test_link_is_converted():
    assert to_telegram_html("[текст](https://ya.ru)") == '<a href="https://ya.ru">текст</a>'


def test_heading_becomes_bold_line():
    """Заголовки Telegram не поддерживает; без обработки в канал уходит «## Вывод»."""
    assert to_telegram_html("## Вывод") == "<b>Вывод</b>"


def test_strike_and_underline():
    assert to_telegram_html("~~зачёркнуто~~") == "<s>зачёркнуто</s>"
    assert to_telegram_html("__подчёркнуто__") == "<u>подчёркнуто</u>"


def test_multiline_post_keeps_structure():
    src = "*Правило*\n\nПервое — _не ныть_.\nВторое — [читать](https://ya.ru)."
    out = to_telegram_html(src)
    assert out.count("\n") == src.count("\n")
    assert tags(out) <= ALLOWED


# --- НЕразметка: главный источник поломок -----------------------------------

def test_unbalanced_star_stays_plain_text():
    """Ровно то, на чём старый Markdown-режим отдавал 400 «can't parse
    entities» и пост уходил в канал без всякого оформления."""
    out = to_telegram_html("Позвонил в 8* утра и всё")
    assert out == "Позвонил в 8* утра и всё"
    assert not tags(out)


def test_snake_case_is_not_italic():
    """«my_report_final» — имя файла, а не курсив. Раньше такие подчёркивания
    и рвали разбор."""
    assert to_telegram_html("файл my_report_final готов") == "файл my_report_final готов"


def test_username_with_underscores_survives():
    assert to_telegram_html("писал @lis_martovskiy вчера") == "писал @lis_martovskiy вчера"


def test_angle_brackets_are_escaped():
    """Без экранирования «<» Telegram посчитал бы это открытием тега и
    отверг всё сообщение целиком."""
    assert to_telegram_html("5 < 7 и a > b") == "5 &lt; 7 и a &gt; b"


def test_ampersand_is_escaped():
    assert to_telegram_html("Тинькофф & партнёры") == "Тинькофф &amp; партнёры"


def test_html_lookalike_in_source_text_is_neutralized():
    """Текст источника мог содержать что угодно, включая обрывки тегов."""
    out = to_telegram_html("написал <b>привет</b> и ушёл")
    assert "&lt;b&gt;" in out
    assert not tags(out)


def test_javascript_url_is_not_turned_into_a_link():
    """Ссылку в посте пользователь открывает одним касанием, без
    предупреждения — схему пускаем только внятную."""
    out = to_telegram_html("[жми](javascript:alert(1))")
    assert "<a" not in out
    assert "javascript" in out


def test_code_span_content_is_not_parsed_as_markup():
    out = to_telegram_html("вызов `a *b* c`")
    assert out == "вызов <code>a *b* c</code>"


def test_only_telegram_tags_are_emitted():
    """Сводный: что бы ни пришло на вход, наружу выходят только теги, которые
    Telegram понимает."""
    messy = (
        "## Итог\n**жирный** _курсив_ ~~зачёркнуто~~ `код` <div>чужое</div>\n"
        "[ссылка](https://ya.ru) и одинокая * и _хвост\n"
        "файл my_file.txt, ник @some_user, 5 < 7 & 8 > 2"
    )
    out = to_telegram_html(messy)
    assert tags(out) <= ALLOWED, tags(out) - ALLOWED


def test_empty_input():
    assert to_telegram_html("") == ""


# --- найдено фаззингом ------------------------------------------------------

def test_crossed_markers_fall_back_to_plain():
    """Маркеры могут пересекаться: «**жирный _и** курсив_» даёт теги, каждый
    из которых закрыт, но вложенность нарушена — Telegram отвечает 400 так же,
    как на незакрытые. Рассуждением этот случай не находится, нашёлся
    фаззингом. Лучше выпустить пост без оформления, чем не выпустить."""
    out = to_telegram_html("**жирный _и** курсив_")
    assert not tags(out)
    assert "жирный" in out and "курсив" in out


def test_internal_placeholder_never_leaks():
    """Код-спан может поглотить плейсхолдер блока кода. При восстановлении в
    прямом порядке вложенный плейсхолдер вставлялся уже после своей очереди и
    уходил в сообщение сырым — «\\x000\\x00» прямо в посте."""
    out = to_telegram_html("`)__'```]@user_name_```]`")
    assert "\x00" not in out


def test_brackets_that_are_not_a_link_are_escaped_once():
    """Двойное экранирование показывало пользователю «&amp;» буквально."""
    assert to_telegram_html("[текст](не-ссылка&лол)") == "[текст](не-ссылка&amp;лол)"


def test_apostrophe_is_not_turned_into_numeric_entity():
    """html.escape по умолчанию даёт «&#x27;», а Telegram числовые сущности
    не разбирает — апостроф показался бы как есть, кодом."""
    assert to_telegram_html("it's fine") == "it's fine"
    assert to_telegram_html('он сказал "да"') == 'он сказал "да"'


def test_fuzz_output_is_always_parseable():
    """Сводный сторож: что бы ни пришло, наружу выходит либо валидная
    вложенность тегов, либо чистый текст. Сид фиксирован, чтобы падение
    воспроизводилось."""
    import random

    from core.services.tg_format import _is_well_formed

    pieces = ["*", "_", "**", "__", "~~", "`", "[", "]", "(", ")", "<", ">", "&",
              "текст", " ", "\n", "@user_name", "my_file.txt", "https://ya.ru",
              "8*", "#", "```", "[ссылка](https://ya.ru)", "'", '"']
    rnd = random.Random(20260728)
    for _ in range(3000):
        src = "".join(rnd.choice(pieces) for _ in range(rnd.randint(1, 26)))
        out = to_telegram_html(src)
        assert _is_well_formed(out), (src, out)
        assert "\x00" not in out, (src, out)
        assert tags(out) <= ALLOWED, (src, out)


# --- служебные строки вокруг поста ------------------------------------------

def test_escape_protects_header_from_channel_title():
    """parse_mode действует на сообщение целиком: «<» в названии чужого канала
    сломал бы карточку, в которой сам пост размечен верно."""
    assert escape("Бизнес <Психология>") == "Бизнес &lt;Психология&gt;"


def test_editor_card_is_valid_html():
    """Сборка карточки целиком — шапка плюс тело."""
    from interfaces.bots.handlers.editor_review import build_editor_text

    card = build_editor_text("Канал <A&B>", "_курсив_ и 5 < 7", 23.0)
    assert "<i>курсив</i>" in card
    assert "&lt;A&amp;B&gt;" in card
    assert tags(card) <= ALLOWED
