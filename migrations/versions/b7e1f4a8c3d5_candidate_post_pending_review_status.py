"""candidate_posts pending_review status

Revision ID: b7e1f4a8c3d5
Revises: a3f6c9d1e0b2
Create Date: 2026-07-21 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e1f4a8c3d5'
down_revision: Union[str, None] = 'a3f6c9d1e0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres хранит sa.Enum по имени члена Python-enum (см. миграцию
    # fe24d8f8f3a0: 'NEW', 'SCORING', ... — заглавные), не по .value.
    # ADD VALUE не может использоваться в той же транзакции, где добавлен —
    # здесь это не нужно: значение просто становится доступным для новых строк.
    op.execute("ALTER TYPE candidatepoststatus ADD VALUE IF NOT EXISTS 'PENDING_REVIEW'")


def downgrade() -> None:
    # Postgres не поддерживает DROP VALUE у enum — откат оставляет значение в
    # типе неиспользуемым (то же ограничение, с которым приходится мириться в
    # большинстве Alembic-проектов при добавлении enum-значений).
    pass
