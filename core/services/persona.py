"""Компиляция конструктора персоны (channel_bots.persona_config) в системный
промпт рерайта — единственная точка сборки, её используют scheduler,
force_generate, digest и песочница preview-rewrite. Структурные поля
(тон/длина/эмодзи/обращение/смелость/стоп-слова/примеры) переводятся в
русскоязычные инструкции; свободный текст persona_prompt («особые указания»)
добавляется в конец и остаётся единственным источником стиля для ботов,
у которых конструктор не заполнен (обратная совместимость)."""

TONE_PRESETS: dict[str, str] = {
    "brash": (
        "Пиши дерзко и уверенно, от первого лица, как живой автор-блогер со своим "
        "мнением. Никакого канцелярита и обтекаемых формулировок."
    ),
    "expert": (
        "Пиши как спокойный эксперт: по делу, с фактами и конкретикой, без "
        "восклицаний и кликбейта. Уверенный, ровный тон."
    ),
    "friendly": (
        "Пиши тепло и по-дружески, разговорным языком, как будто рассказываешь "
        "знакомому. Просто о сложном, без назидательности."
    ),
    "news": (
        "Пиши в новостном стиле: сначала суть, затем детали. Нейтрально, кратко, "
        "без оценок и лишних эпитетов."
    ),
}

LENGTH_RULES: dict[str, str] = {
    "shorter": "Делай пост заметно короче исходника — оставляй только самое сильное.",
    "same": "Держи длину примерно как у исходника.",
    "longer": "Разворачивай мысль подробнее исходника, добавляй контекст и вывод.",
}

EMOJI_RULES: dict[str, str] = {
    "none": "Эмодзи не используй совсем.",
    "few": "Эмодзи используй умеренно — одно-два на пост, только там, где усиливают.",
    "many": "Эмодзи используй активно, в том числе в начале абзацев.",
}

ADDRESS_RULES: dict[str, str] = {
    "ty": "Обращайся к читателю на «ты».",
    "vy": "Обращайся к читателю на «вы».",
    "neutral": "Пиши безлично, без прямого обращения к читателю.",
}

BOLDNESS_RULES: dict[int, str] = {
    1: "Переписывай осторожно: сохраняй структуру и почти все факты исходника, меняй только формулировки.",
    2: "Переписывай сдержанно: близко к исходнику, но своими словами.",
    3: "Переписывай уверенно: сохраняй суть, но подачу выстраивай по-своему.",
    4: "Переписывай смело: бери из исходника только идею и факты, композицию и подачу делай полностью свои.",
    5: "Переосмысляй полностью: исходник — лишь повод, пост должен читаться как самостоятельный авторский материал.",
}


def build_persona_prompt(persona_config: dict | None, custom: str) -> str:
    """Собирает системный промпт из конструктора + свободного текста.
    Пустой конфиг -> голый custom (прежнее поведение)."""
    config = persona_config or {}
    custom = (custom or "").strip()
    if not config:
        return custom

    parts: list[str] = []

    tone = config.get("tone")
    if tone == "custom":
        tone_custom = str(config.get("tone_custom") or "").strip()
        if tone_custom:
            parts.append(tone_custom)
    elif tone in TONE_PRESETS:
        parts.append(TONE_PRESETS[tone])

    for key, rules in (("length", LENGTH_RULES), ("emoji", EMOJI_RULES), ("address", ADDRESS_RULES)):
        value = config.get(key)
        if value in rules:
            parts.append(rules[value])

    boldness = config.get("boldness")
    if isinstance(boldness, int) and boldness in BOLDNESS_RULES:
        parts.append(BOLDNESS_RULES[boldness])

    stop_words = [str(w).strip() for w in (config.get("stop_words") or []) if str(w).strip()]
    if stop_words:
        parts.append("Никогда не используй эти слова, обороты и темы: " + ", ".join(stop_words) + ".")

    hashtags = str(config.get("hashtags") or "").strip()
    if hashtags:
        parts.append(f"В конце поста добавляй хэштеги: {hashtags}")

    examples_good = [str(e).strip() for e in (config.get("examples_good") or []) if str(e).strip()]
    if examples_good:
        joined = "\n---\n".join(examples_good[:5])
        parts.append("Вот примеры постов в правильном стиле — попади в этот голос:\n" + joined)

    examples_bad = [str(e).strip() for e in (config.get("examples_bad") or []) if str(e).strip()]
    if examples_bad:
        joined = "\n---\n".join(examples_bad[:3])
        parts.append("А вот так писать НЕ надо — избегай такого тона и подачи:\n" + joined)

    if custom:
        parts.append(f"Особые указания: {custom}")

    return "\n\n".join(parts)
