"""candidate_posts media reference (has_media, media_group_id)

Revision ID: a7d2f4e9c1b8
Revises: f1b8e3c6a2d9
Create Date: 2026-07-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7d2f4e9c1b8'
down_revision: Union[str, None] = 'f1b8e3c6a2d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'candidate_posts',
        sa.Column('has_media', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'candidate_posts',
        sa.Column('media_group_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('candidate_posts', 'media_group_id')
    op.drop_column('candidate_posts', 'has_media')
