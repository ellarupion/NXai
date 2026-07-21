"""target_channels.crosspost (VK/MAX cross-post config)

Revision ID: a1c5e9b2d768
Revises: f4b9c1e2a785
Create Date: 2026-07-22 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1c5e9b2d768'
down_revision: Union[str, None] = 'f4b9c1e2a785'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'target_channels',
        sa.Column('crosspost', postgresql.JSONB(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('target_channels', 'crosspost')
