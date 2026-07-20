"""AdminService — логин/пароль вход в панель (адаптировано из NX
core/services/admin.py без изменений в форме). Первый админ заводится через
scripts/create_admin.py."""

from uuid import UUID

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models.admin import Admin

logger = get_logger(__name__)

MAX_PASSWORD_BYTES = 72

_DECOY_HASH = bcrypt.hashpw(b"decoy", bcrypt.gensalt())


class AdminAlreadyExistsError(Exception):
    pass


class PasswordTooLongError(Exception):
    pass


class LastSuperadminError(Exception):
    pass


def _hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(f"Пароль длиннее {MAX_PASSWORD_BYTES} байт")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_admin(self, username: str, password: str, is_superadmin: bool = False) -> Admin:
        admin = Admin(username=username, password_hash=_hash_password(password), is_superadmin=is_superadmin)
        self.session.add(admin)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AdminAlreadyExistsError(f"Admin «{username}» уже существует") from exc
        logger.info("admin.created", admin_id=str(admin.id), username=username)
        return admin

    async def verify_password(self, username: str, password: str) -> Admin | None:
        """Единая точка выхода что для "нет такого username", что для "неверный
        пароль" — чтобы наружу не утекало, какой из двух случаев произошёл
        (тот же timing-safe паттерн с decoy-хешем, что в NX)."""
        result = await self.session.execute(select(Admin).where(Admin.username == username))
        admin = result.scalar_one_or_none()
        if admin is None:
            bcrypt.checkpw(b"decoy", _DECOY_HASH)
            return None
        if not bcrypt.checkpw(password.encode("utf-8"), admin.password_hash.encode("ascii")):
            return None
        return admin

    async def delete_admin(self, admin_id: UUID, current_admin_id: UUID) -> None:
        if admin_id == current_admin_id:
            raise ValueError("Нельзя удалить собственную учётную запись")
        admin = await self.session.get(Admin, admin_id)
        if admin is None:
            return
        if admin.is_superadmin and await self._superadmin_count() <= 1:
            raise LastSuperadminError("Нельзя удалить последнего суперадмина")
        await self.session.delete(admin)
        await self.session.flush()

    async def _superadmin_count(self) -> int:
        count = await self.session.scalar(
            select(func.count()).select_from(Admin).where(Admin.is_superadmin.is_(True))
        )
        return count or 0
