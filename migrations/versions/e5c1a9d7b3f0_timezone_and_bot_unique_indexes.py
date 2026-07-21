"""panel_settings.timezone + partial unique indexes on channel_bots

Revision ID: e5c1a9d7b3f0
Revises: d2a9f0c1b6e4
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5c1a9d7b3f0'
down_revision: Union[str, None] = 'd2a9f0c1b6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'panel_settings',
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='Europe/Moscow'),
    )
    # Партиал-уникальность: один активный THEME-бот на тему, один активный
    # ADMIN-бот всего. role хранится как метка enum'а botrole в верхнем регистре.
    op.create_index(
        'uq_channel_bots_active_theme',
        'channel_bots',
        ['theme_id'],
        unique=True,
        postgresql_where=sa.text("role = 'THEME' AND is_active"),
    )
    op.create_index(
        'uq_channel_bots_active_admin',
        'channel_bots',
        ['role'],
        unique=True,
        postgresql_where=sa.text("role = 'ADMIN' AND is_active"),
    )


def downgrade() -> None:
    op.drop_index('uq_channel_bots_active_admin', table_name='channel_bots')
    op.drop_index('uq_channel_bots_active_theme', table_name='channel_bots')
    op.drop_column('panel_settings', 'timezone')
