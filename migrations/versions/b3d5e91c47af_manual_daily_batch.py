"""Ручной режим темы и дневная партия постов

Пайплайн был устроен как непрерывный конвейер: планировщик каждые пять минут
брал отобранных кандидатов и переписывал их через LLM. На теме с 12
источниками это давало десятки постов в сутки, все — в «Проверку». Оператору
столько не нужно, а платит он за каждый.

manual_mode — тема готовит посты только по просьбе («Посты на сегодня»),
фоновый рерайт её не трогает. Включён по умолчанию И для новых тем, И для
существующих (server_default="true"): непрерывный конвейер оказался не тем
поведением, которое стоит держать умолчанием — в него теперь входят осознанно.

daily_batch_date + daily_batch_size — сколько постов заказано на сегодня.
По ним считается «долг»: заказали 5, три одобрены, один отклонён, один ждёт —
значит должен доехать ещё один, взамен отклонённого. Замену готовит
планировщик на ближайшем тике, а не запрос на отклонение: рерайт это секунды
ожидания LLM, и держать на них открытым HTTP-запрос панели незачем.

candidate_posts.batch_date — к партии какого дня относится пост. Без этой
пометки долг считать не по чему: «сколько постов темы одобрено сегодня» — не
то же самое, что «сколько из заказанных доехало». Тема могла одобрять посты,
приготовленные до перехода в ручной режим, и они молча гасили бы заказ,
которого не выполняли.

Revision ID: b3d5e91c47af
Revises: a7c3f01b9d24
Create Date: 2026-07-28 18:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d5e91c47af'
down_revision: Union[str, None] = 'a7c3f01b9d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "themes",
        sa.Column("manual_mode", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("themes", sa.Column("daily_batch_date", sa.Date(), nullable=True))
    op.add_column(
        "themes",
        sa.Column("daily_batch_size", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("candidate_posts", sa.Column("batch_date", sa.Date(), nullable=True))
    op.create_index("ix_candidate_posts_batch_date", "candidate_posts", ["batch_date"])


def downgrade() -> None:
    op.drop_index("ix_candidate_posts_batch_date", table_name="candidate_posts")
    op.drop_column("candidate_posts", "batch_date")
    op.drop_column("themes", "daily_batch_size")
    op.drop_column("themes", "daily_batch_date")
    op.drop_column("themes", "manual_mode")
