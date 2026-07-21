"""Encrypt existing bot_token / session_string secrets at rest

Revision ID: e8f1a3d7c904
Revises: d9a4c2e8b6f1
Create Date: 2026-07-22 22:00:00.000000

Столбцы остаются TEXT — шифрование прозрачно на уровне ORM-типа
(core/models/types.py:EncryptedText). Эта миграция лишь ре-шифрует уже
лежащие в БД plaintext-значения; читаются они и без миграции (EncryptedText
возвращает легаси-plaintext как есть), но лучше зашифровать сразу.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e8f1a3d7c904'
down_revision: Union[str, None] = 'd9a4c2e8b6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _encrypt_column(conn, table: str, column: str) -> None:
    from core.crypto import ENC_PREFIX, encrypt

    rows = conn.execute(sa.text(f"SELECT id, {column} FROM {table}")).fetchall()
    for row_id, value in rows:
        if value is None or value == "" or value.startswith(ENC_PREFIX):
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
            {"v": encrypt(value), "id": row_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _encrypt_column(conn, "channel_bots", "bot_token")
    _encrypt_column(conn, "telethon_sessions", "session_string")


def downgrade() -> None:
    # Расшифровка обратно в plaintext — на случай отката; требует того же ключа.
    conn = op.get_bind()
    from core.crypto import ENC_PREFIX, decrypt

    for table, column in (("channel_bots", "bot_token"), ("telethon_sessions", "session_string")):
        rows = conn.execute(sa.text(f"SELECT id, {column} FROM {table}")).fetchall()
        for row_id, value in rows:
            if value and value.startswith(ENC_PREFIX):
                conn.execute(
                    sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
                    {"v": decrypt(value), "id": row_id},
                )
