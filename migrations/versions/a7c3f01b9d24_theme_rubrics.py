"""Рубрики темы и рубрика кандидата

Тема — это ниша целиком («мужской канал»), но внутри неё контент делится на
подтемы: деньги, отношения, здоровье, карьера. Без такого деления канал
выдаёт всё подряд, и легко получается день из пяти постов про деньги —
источники в один день пишут об одном, скоринг это только усиливает
(виральное в нише обычно виральное у всех сразу).

themes.rubrics — список рубрик темы (JSONB-массив строк), задаётся оператором.
candidate_posts.rubric — к какой из них отнесён пост; NULL значит «ещё не
классифицирован» или «рубрики у темы не заданы». Строкой, а не FK: рубрики
редактируются свободно, и переименование не должно ломать историю постов —
старое значение просто перестаёт совпадать со списком, что честнее каскада.

Revision ID: a7c3f01b9d24
Revises: e5b8d2f4a917
Create Date: 2026-07-28 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c3f01b9d24'
down_revision: Union[str, None] = 'e5b8d2f4a917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "themes",
        sa.Column(
            "rubrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column("candidate_posts", sa.Column("rubric", sa.String(length=64), nullable=True))
    # Индекс под выборку «последние опубликованные рубрики темы» — её делает
    # планировщик на каждый слот, чтобы не ставить подряд две про одно и то же.
    op.create_index("ix_candidate_posts_rubric", "candidate_posts", ["rubric"])


def downgrade() -> None:
    op.drop_index("ix_candidate_posts_rubric", table_name="candidate_posts")
    op.drop_column("candidate_posts", "rubric")
    op.drop_column("themes", "rubrics")
