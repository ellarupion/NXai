"""channel_bots: editor_chat_id / use_media / autopublish_enabled

Revision ID: e5b8d2f4a917
Revises: d1a7c9e3b582
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5b8d2f4a917'
down_revision: Union[str, None] = 'd1a7c9e3b582'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_bots', sa.Column('editor_chat_id', sa.BigInteger(), nullable=True))
    op.add_column(
        'channel_bots',
        sa.Column('use_media', sa.Boolean(), nullable=False, server_default='false'),
    )
    # autopublish выключен и для существующих ботов — по требованию режима
    # обкатки: пока рерайт не выстроен, бот сам в канал ничего не ставит;
    # включается тумблером в панели.
    op.add_column(
        'channel_bots',
        sa.Column('autopublish_enabled', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('channel_bots', 'autopublish_enabled')
    op.drop_column('channel_bots', 'use_media')
    op.drop_column('channel_bots', 'editor_chat_id')
