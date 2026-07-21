"""themes digest settings (digest_enabled, digest_hour)

Revision ID: d9a4c2e8b6f1
Revises: c3e7b1f95d2a
Create Date: 2026-07-22 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9a4c2e8b6f1'
down_revision: Union[str, None] = 'c3e7b1f95d2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('themes', sa.Column('digest_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('themes', sa.Column('digest_hour', sa.Integer(), nullable=False, server_default='9'))


def downgrade() -> None:
    op.drop_column('themes', 'digest_hour')
    op.drop_column('themes', 'digest_enabled')
