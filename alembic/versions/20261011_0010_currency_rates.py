"""Persist imported currency-rate snapshots without changing monetary documents.

Revision ID: 20261011_0010
Revises: 20261006_0009
"""

import sqlalchemy as sa

from alembic import op

revision = "20261011_0010"
down_revision = "20261006_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "configuration_currency_rate_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "base_currency_id",
            sa.String(36),
            sa.ForeignKey("configuration_currencies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("base_code", sa.String(3), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("missing_codes", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_currency_rate_batches_base_date",
        "configuration_currency_rate_batches",
        ["base_currency_id", "fetched_at", "id"],
    )
    op.create_table(
        "configuration_currency_rates",
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("configuration_currency_rate_batches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("quote_code", sa.String(3), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(38, 18), nullable=False),
    )


def downgrade():
    op.drop_table("configuration_currency_rates")
    op.drop_table("configuration_currency_rate_batches")
