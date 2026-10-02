"""Add structured user names.

Revision ID: 20260929_0007
Revises: 20260921_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0007"
down_revision: str | None = "20260921_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("identity_users", sa.Column("first_name", sa.String(100)))
    op.add_column("identity_users", sa.Column("last_name", sa.String(100)))


def downgrade() -> None:
    op.drop_column("identity_users", "last_name")
    op.drop_column("identity_users", "first_name")
