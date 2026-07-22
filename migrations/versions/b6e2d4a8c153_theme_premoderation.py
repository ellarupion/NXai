"""themes.premoderation (рерайты темы через Проверку, а не сразу в автопаблиш)

Revision ID: b6e2d4a8c153
Revises: a1c5e9b2d768
Create Date: 2026-07-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6e2d4a8c153'
down_revision: Union[str, None] = 'a1c5e9b2d768'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='false': существующие темы не меняют поведение — их
    # рерайты продолжают идти в автопаблиш напрямую. Новые темы получают
    # премодерацию через ORM-default (core/models/theme.py).
    op.add_column(
        'themes',
        sa.Column('premoderation', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('themes', 'premoderation')
