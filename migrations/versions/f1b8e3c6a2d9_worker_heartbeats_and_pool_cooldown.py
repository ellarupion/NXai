"""worker_heartbeats table + panel_settings.pool_cooldown_days

Revision ID: f1b8e3c6a2d9
Revises: e5c1a9d7b3f0
Create Date: 2026-07-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1b8e3c6a2d9'
down_revision: Union[str, None] = 'e5c1a9d7b3f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_heartbeats',
        sa.Column('worker_name', sa.String(length=64), nullable=False),
        sa.Column('last_beat_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('detail', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('worker_name'),
    )
    op.add_column(
        'panel_settings',
        sa.Column('pool_cooldown_days', sa.Integer(), nullable=False, server_default='7'),
    )


def downgrade() -> None:
    op.drop_column('panel_settings', 'pool_cooldown_days')
    op.drop_table('worker_heartbeats')
