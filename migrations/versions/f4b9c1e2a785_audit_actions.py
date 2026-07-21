"""Add login/approve/bot_token_change to auditaction enum

Revision ID: f4b9c1e2a785
Revises: e8f1a3d7c904
Create Date: 2026-07-22 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4b9c1e2a785'
down_revision: Union[str, None] = 'e8f1a3d7c904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE IF NOT EXISTS работает в транзакции в PG 12+, пока новое
    # значение не используется в той же транзакции (мы его тут не используем).
    for value in ("LOGIN", "APPROVE", "BOT_TOKEN_CHANGE"):
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Удаление значений из enum PostgreSQL не поддерживает — оставляем как есть.
    pass
