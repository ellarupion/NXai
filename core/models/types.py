"""EncryptedText — SQLAlchemy-тип, прозрачно шифрующий значение при записи и
расшифровывающий при чтении (core/crypto.py). Позволяет защитить секреты в
БД (bot_token, session_string — аудит, п.8.1), не трогая ни одного места, где
эти поля читаются/пишутся: для остального кода это обычная строка."""

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from core.crypto import decrypt, encrypt


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt(value)
