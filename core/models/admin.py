from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Admin(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Аккаунт входа в панель (логин/пароль, bcrypt-хеш) — перенесено из NX
    без изменений. Создаётся только через scripts/create_admin.py."""

    __tablename__ = "admins"

    username: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
