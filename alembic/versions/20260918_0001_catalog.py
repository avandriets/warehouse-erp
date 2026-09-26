"""Create product catalog tables.

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_catalog_categories_active_name", "catalog_categories", ["active", "name"])

    op.create_table(
        "catalog_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("precision", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "`precision` >= 0 AND `precision` <= 6",
            name="ck_catalog_unit_precision",
        ),
    )

    op.create_table(
        "catalog_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "category_id",
            sa.String(36),
            sa.ForeignKey("catalog_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_catalog_products_category_active", "catalog_products", ["category_id", "active"]
    )
    op.create_index("ix_catalog_products_name", "catalog_products", ["name"])

    op.create_table(
        "catalog_skus",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "product_id",
            sa.String(36),
            sa.ForeignKey("catalog_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            sa.String(36),
            sa.ForeignKey("catalog_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("barcode", sa.String(128), nullable=True, unique=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("tracking_mode", sa.String(16), nullable=False),
        sa.Column("issue_strategy", sa.String(16), nullable=False),
        sa.Column("negative_stock_allowed", sa.Boolean(), nullable=False),
        sa.Column("expiry_required", sa.Boolean(), nullable=False),
        sa.Column("mrp_tracking_enabled", sa.Boolean(), nullable=False),
        sa.Column("quality_tracking_enabled", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tracking_mode IN ('NONE', 'BATCH')", name="ck_sku_tracking_mode"),
        sa.CheckConstraint(
            "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')", name="ck_sku_issue_strategy"
        ),
        sa.CheckConstraint(
            "expiry_required = false OR tracking_mode = 'BATCH'",
            name="ck_sku_expiry_requires_batch",
        ),
        sa.CheckConstraint(
            "issue_strategy != 'FEFO' OR tracking_mode = 'BATCH'",
            name="ck_sku_fefo_requires_batch",
        ),
    )
    op.create_index("ix_catalog_skus_product_active", "catalog_skus", ["product_id", "active"])


def downgrade() -> None:
    op.drop_index("ix_catalog_skus_product_active", table_name="catalog_skus")
    op.drop_table("catalog_skus")
    op.drop_index("ix_catalog_products_name", table_name="catalog_products")
    op.drop_index("ix_catalog_products_category_active", table_name="catalog_products")
    op.drop_table("catalog_products")
    op.drop_table("catalog_units")
    op.drop_index("ix_catalog_categories_active_name", table_name="catalog_categories")
    op.drop_table("catalog_categories")
