"""encrypt pii fields (users.full_name, candidates.phone)

Converts ``users.full_name`` and ``candidates.phone`` from plaintext
``String`` columns to Fernet-encrypted ``BYTEA``. Any existing plaintext
values are encrypted in place during the upgrade; downgrade decrypts them
back to plaintext.

Revision ID: abcc24b78e0c
Revises: 141b74ef816a
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from cryptography.fernet import Fernet, MultiFernet

from alembic import op
from app.core.config import settings

revision: str = "abcc24b78e0c"
down_revision: str | Sequence[str] | None = "141b74ef816a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FIELDS: list[tuple[str, str]] = [
    ("users", "full_name"),
    ("candidates", "phone"),
]


def _cipher() -> MultiFernet:
    keys = settings.encryption_keys
    if not keys:
        raise RuntimeError("ENCRYPTION_KEYS must be set before running this migration.")
    return MultiFernet([Fernet(k.get_secret_value().encode()) for k in keys])


def upgrade() -> None:
    bind = op.get_bind()
    cipher = _cipher()

    for table, column in _FIELDS:
        op.add_column(
            table, sa.Column(f"{column}_enc", sa.LargeBinary(), nullable=True)
        )

        rows = bind.execute(
            sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
        ).all()
        for row_id, plaintext in rows:
            bind.execute(
                sa.text(f"UPDATE {table} SET {column}_enc = :enc WHERE id = :id"),
                {"enc": cipher.encrypt(plaintext.encode("utf-8")), "id": row_id},
            )

        op.drop_column(table, column)
        op.alter_column(table, f"{column}_enc", new_column_name=column)


def downgrade() -> None:
    bind = op.get_bind()
    cipher = _cipher()

    for table, column in _FIELDS:
        op.add_column(
            table, sa.Column(f"{column}_plain", sa.String(length=500), nullable=True)
        )

        rows = bind.execute(
            sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
        ).all()
        for row_id, ciphertext in rows:
            bind.execute(
                sa.text(f"UPDATE {table} SET {column}_plain = :plain WHERE id = :id"),
                {
                    "plain": cipher.decrypt(bytes(ciphertext)).decode("utf-8"),
                    "id": row_id,
                },
            )

        op.drop_column(table, column)
        op.alter_column(table, f"{column}_plain", new_column_name=column)
