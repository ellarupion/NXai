"""Одноразовый интерактивный вход в Telegram под аккаунтом-читалкой — генерирует
session string для одного элемента пула Telethon-сессий (см.
core/models/telethon_session.py, ARCHITECTURE.md §7: несколько таких аккаунтов
шардируют список source_channels между собой).

Нужно на каждый новый аккаунт пула:
    1. Зарегистрировать приложение на https://my.telegram.org -> API development
       tools (api_id/api_hash общие для всех сессий одного пула, задаются в .env).
    2. Запустить локально (не в докере — нужен интерактивный ввод):
           TELEGRAM_API_ID=... TELEGRAM_API_HASH=... python scripts/generate_telethon_session.py
    3. Ввести номер телефона, код из Telegram (и пароль 2FA, если включён).
    4. Добавить полученный session string в панели как новую TelethonSession
       (или напрямую в БД на раннем этапе, пока в панели ещё нет формы — см.
       ROADMAP.md Phase 1) и подписать этот аккаунт на нужные source_channels.

Сессия даёт полный доступ к аккаунту на уровне MTProto — храните session
string как секрет, никогда не коммитьте в репозиторий."""

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()
        print("\nГотово! Session string для новой TelethonSession:\n")
        print(session_string)
        print()


if __name__ == "__main__":
    asyncio.run(main())
