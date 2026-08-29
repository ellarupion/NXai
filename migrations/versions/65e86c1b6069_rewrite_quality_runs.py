"""Замеры качества рерайта: таблицы прогонов и пар.

Плюс новый раздел расходов QUALITY — его alembic autogenerate не заметил бы: он
сравнивает таблицы и колонки, а не содержимое типов-перечислений. Без этой строки
первый же замер упал бы на записи расхода.

В downgrade типы удаляются явно: op.drop_table их не трогает, и после отката в базе
осталось бы два осиротевших типа, из-за которых повторный upgrade падал бы с
«type already exists».

Revision ID: 65e86c1b6069
Revises: afd997dddae7
Create Date: 2026-08-29 14:44:18.434784
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "65e86c1b6069"
down_revision: str | None = "afd997dddae7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE llmusagekind ADD VALUE IF NOT EXISTS 'QUALITY'")

    op.create_table(
        "rewrite_quality_runs",
        sa.Column("theme_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("baseline_persona", sa.Text(), nullable=False),
        sa.Column("variant_persona", sa.Text(), nullable=False),
        sa.Column("baseline_model", sa.String(length=120), nullable=False),
        sa.Column("variant_model", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "DONE", "FAILED", name="qualityrunstatus"),
            nullable=False,
        ),
        sa.Column("wins_baseline", sa.Integer(), nullable=False),
        sa.Column("wins_variant", sa.Integer(), nullable=False),
        sa.Column("ties", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # SET NULL, а не CASCADE: вывод «эта персона писала лучше» ценен и после того,
        # как тему закрыли.
        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rewrite_quality_runs_status"), "rewrite_quality_runs", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_rewrite_quality_runs_theme_id"),
        "rewrite_quality_runs",
        ["theme_id"],
        unique=False,
    )

    op.create_table(
        "rewrite_quality_pairs",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("baseline_text", sa.Text(), nullable=False),
        sa.Column("variant_text", sa.Text(), nullable=False),
        sa.Column(
            "verdict_direct",
            sa.Enum("BASELINE", "VARIANT", "TIE", name="qualityverdict"),
            nullable=True,
        ),
        sa.Column(
            "verdict_swapped",
            sa.Enum("BASELINE", "VARIANT", "TIE", name="qualityverdict"),
            nullable=True,
        ),
        sa.Column(
            "verdict",
            sa.Enum("BASELINE", "VARIANT", "TIE", name="qualityverdict"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["rewrite_quality_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rewrite_quality_pairs_run_id"), "rewrite_quality_pairs", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_rewrite_quality_pairs_verdict"),
        "rewrite_quality_pairs",
        ["verdict"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rewrite_quality_pairs_verdict"), table_name="rewrite_quality_pairs")
    op.drop_index(op.f("ix_rewrite_quality_pairs_run_id"), table_name="rewrite_quality_pairs")
    op.drop_table("rewrite_quality_pairs")
    op.drop_index(op.f("ix_rewrite_quality_runs_theme_id"), table_name="rewrite_quality_runs")
    op.drop_index(op.f("ix_rewrite_quality_runs_status"), table_name="rewrite_quality_runs")
    op.drop_table("rewrite_quality_runs")
    op.execute("DROP TYPE IF EXISTS qualityverdict")
    op.execute("DROP TYPE IF EXISTS qualityrunstatus")
    # Значение QUALITY в llmusagekind остаётся: Postgres не умеет удалять значение из
    # перечисления, а пересоздавать тип нельзя — на него ссылается история расходов.
