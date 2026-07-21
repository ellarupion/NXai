"""target_channels.metrics_session_id (publication metrics reader)

Revision ID: c3e7b1f95d2a
Revises: a7d2f4e9c1b8
Create Date: 2026-07-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3e7b1f95d2a'
down_revision: Union[str, None] = 'a7d2f4e9c1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'target_channels',
        sa.Column('metrics_session_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_target_channels_metrics_session_id',
        'target_channels',
        'telethon_sessions',
        ['metrics_session_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_target_channels_metrics_session_id', 'target_channels', type_='foreignkey')
    op.drop_column('target_channels', 'metrics_session_id')
