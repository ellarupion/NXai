"""panel_settings telegram overrides

Revision ID: a3f6c9d1e0b2
Revises: fe24d8f8f3a0
Create Date: 2026-07-21 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f6c9d1e0b2'
down_revision: Union[str, None] = 'fe24d8f8f3a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'panel_settings',
        sa.Column('telegram_api_id_override', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'panel_settings',
        sa.Column('telegram_api_hash_override', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('panel_settings', 'telegram_api_hash_override')
    op.drop_column('panel_settings', 'telegram_api_id_override')
