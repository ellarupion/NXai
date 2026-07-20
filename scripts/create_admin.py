"""Заводит администратора веб-панели (логин/пароль) — адаптировано из NX
scripts/create_admin.py без изменений в форме. Единственный способ создать
первого админа: своей регистрации в UI нет намеренно.

Использование:
    python scripts/create_admin.py --username admin
    python scripts/create_admin.py --username admin --superadmin
"""

import argparse
import asyncio
import getpass

from core.db import get_session_factory
from core.services.admin import AdminAlreadyExistsError, AdminService, PasswordTooLongError


async def create_admin(username: str, password: str, is_superadmin: bool) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            admin = await AdminService(session).create_admin(username, password, is_superadmin)
        except AdminAlreadyExistsError as exc:
            print(f"Ошибка: {exc}")
            return
        except PasswordTooLongError as exc:
            print(f"Ошибка: {exc}")
            return
        await session.commit()
        role = "суперадмин" if admin.is_superadmin else "админ"
        print(f"Создан {role}: {admin.username} ({admin.id})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", type=str, required=True)
    parser.add_argument("--superadmin", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    password = getpass.getpass("Пароль: ")
    password_confirm = getpass.getpass("Пароль ещё раз: ")
    if password != password_confirm:
        print("Пароли не совпадают.")
    elif not password:
        print("Пароль не может быть пустым.")
    else:
        asyncio.run(create_admin(args.username, password, args.superadmin))
