"""Прозрачное шифрование секретов, хранящихся в БД (bot_token, session_string —
аудит, п.8.1). Утечка дампа БД без ключа больше не отдаёт контроль над ботами
и читающими аккаунтами.

Шифртекст помечается префиксом ENC_PREFIX. Это позволяет:
  - отличать зашифрованное значение от легаси-plaintext (миграция может идти
    постепенно: старые строки читаются как есть, любая перезапись их
    зашифрует, плюс есть разовый data-migration);
  - не пытаться расшифровать то, что ещё не зашифровано.

Ключ — Fernet (AES-128-CBC + HMAC). Берётся из SECRETS_ENCRYPTION_KEY; если
не задан — детерминированно выводится из api_secret_key (sha256 → urlsafe
base64), чтобы дев/существующие развёртывания работали без новой переменной.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings

ENC_PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.secrets_encryption_key
    if raw:
        # Пользователь задал полноценный Fernet-ключ.
        key = raw.encode("ascii")
    else:
        # Фолбэк: выводим 32-байтный ключ из api_secret_key.
        digest = hashlib.sha256(settings.api_secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Возвращает помеченный шифртекст. Пустую строку не шифруем — храним как
    есть (нет секрета — нечего защищать, и легаси-пустые значения не ломаются)."""
    if not plaintext:
        return plaintext
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{ENC_PREFIX}{token}"


def decrypt(value: str | None) -> str | None:
    """Расшифровывает помеченное значение; легаси-plaintext (без префикса)
    возвращает как есть, чтобы не ломать ещё не мигрированные строки."""
    if not value or not value.startswith(ENC_PREFIX):
        return value
    token = value[len(ENC_PREFIX):].encode("ascii")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken:
        # Неверный ключ/битые данные — не роняем весь процесс на чтении, но
        # это сигнал о смене ключа без ре-шифрования.
        raise ValueError("Не удалось расшифровать секрет — проверьте SECRETS_ENCRYPTION_KEY")


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(ENC_PREFIX)
