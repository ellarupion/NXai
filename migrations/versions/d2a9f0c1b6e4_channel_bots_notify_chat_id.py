"""channel_bots notify_chat_id

Revision ID: d2a9f0c1b6e4
Revises: b7e1f4a8c3d5
Create Date: 2026-07-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2a9f0c1b6e4'
down_revision: Union[str, None] = 'b7e1f4a8c3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_bots', sa.Column('notify_chat_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('channel_bots', 'notify_chat_id')
