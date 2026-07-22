"""channel_bots.persona_config (конструктор персоны)

Revision ID: c8f3b5d9e271
Revises: b6e2d4a8c153
Create Date: 2026-07-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8f3b5d9e271'
down_revision: Union[str, None] = 'b6e2d4a8c153'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # '{}' — существующие боты остаются на голом persona_prompt (фолбэк в
    # core/services/persona.py), поведение не меняется до первого сохранения
    # конструктора из панели.
    op.add_column(
        'channel_bots',
        sa.Column('persona_config', postgresql.JSONB(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('channel_bots', 'persona_config')
