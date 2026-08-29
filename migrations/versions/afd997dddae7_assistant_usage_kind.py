"""Раздел расходов «Вопросы помощнику».

Без него первый же вопрос помощнику падал бы на записи расхода: Postgres хранит в
перечислении ИМЯ члена (ASSISTANT), и нового имени в типе ещё нет.

Написано руками: alembic autogenerate новых членов перечисления не замечает вовсе —
сравнивает таблицы и колонки, а не содержимое типов. Пустая миграция здесь означала бы
не «менять нечего», а «изменение потерялось».

Revision ID: afd997dddae7
Revises: 0f86175ffdef
Create Date: 2026-08-29 14:17:06.041126
"""

from collections.abc import Sequence

from alembic import op

revision: str = "afd997dddae7"
down_revision: str | None = "0f86175ffdef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS — миграция должна переживать повторный накат на базу, где значение
    # уже появилось (например, после отката и повторного обновления).
    op.execute("ALTER TYPE llmusagekind ADD VALUE IF NOT EXISTS 'ASSISTANT'")


def downgrade() -> None:
    # Postgres не умеет удалять значение из перечисления, а пересоздавать тип ради
    # отката нельзя: на него ссылается таблица с историей расходов. Лишнее значение
    # в типе безвредно — строк с ним после отката просто не будет.
    pass
