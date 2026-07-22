"""candidate_posts.rejection_reason («Отклонить с причиной»)

Revision ID: d1a7c9e3b582
Revises: c8f3b5d9e271
Create Date: 2026-07-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1a7c9e3b582'
down_revision: Union[str, None] = 'c8f3b5d9e271'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'candidate_posts',
        sa.Column('rejection_reason', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('candidate_posts', 'rejection_reason')
