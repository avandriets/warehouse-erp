"""Unify products and SKUs and add category hierarchy.

Revision ID: 20260920_0003
Revises: 20260919_0002
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0003"
down_revision: str | None = "20260919_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_empty_catalog() -> None:
    connection = op.get_bind()
    product_count = connection.scalar(sa.text("SELECT COUNT(*) FROM catalog_products"))
    sku_count = connection.scalar(sa.text("SELECT COUNT(*) FROM catalog_skus"))
    if product_count or sku_count:
        raise RuntimeError(
            "Unified-product migration requires an empty product catalog; "
            "migrate existing Product/SKU data explicitly before upgrading"
        )


def upgrade() -> None:
    _require_empty_catalog()

    op.drop_table("catalog_skus")

    with op.batch_alter_table("catalog_categories") as batch:
        batch.add_column(sa.Column("parent_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_catalog_categories_parent",
            "catalog_categories",
            ["parent_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_catalog_categories_parent_name",
            ["parent_id", "name"],
        )

    with op.batch_alter_table("catalog_products") as batch:
        batch.add_column(sa.Column("code", sa.String(64), nullable=True))
        batch.add_column(sa.Column("unit_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("barcode", sa.String(128), nullable=True))
        batch.add_column(
            sa.Column("tracking_mode", sa.String(16), nullable=False, server_default="NONE")
        )
        batch.add_column(
            sa.Column("issue_strategy", sa.String(16), nullable=False, server_default="MANUAL")
        )
        batch.add_column(
            sa.Column(
                "negative_stock_allowed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("expiry_required", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column(
                "mrp_tracking_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "quality_tracking_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_foreign_key(
            "fk_catalog_products_unit",
            "catalog_units",
            ["unit_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_catalog_products_code", ["code"])
        batch.create_unique_constraint("uq_catalog_products_barcode", ["barcode"])
        batch.create_check_constraint(
            "ck_product_tracking_mode",
            "tracking_mode IN ('NONE', 'BATCH')",
        )
        batch.create_check_constraint(
            "ck_product_issue_strategy",
            "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')",
        )
        batch.create_check_constraint(
            "ck_product_expiry_requires_batch",
            "expiry_required = false OR tracking_mode = 'BATCH'",
        )
        batch.create_check_constraint(
            "ck_product_fefo_requires_batch",
            "issue_strategy != 'FEFO' OR tracking_mode = 'BATCH'",
        )
        batch.alter_column("code", existing_type=sa.String(64), nullable=False)
        batch.alter_column("unit_id", existing_type=sa.String(36), nullable=False)
        batch.alter_column("tracking_mode", server_default=None)
        batch.alter_column("issue_strategy", server_default=None)
        batch.alter_column("negative_stock_allowed", server_default=None)
        batch.alter_column("expiry_required", server_default=None)
        batch.alter_column("mrp_tracking_enabled", server_default=None)
        batch.alter_column("quality_tracking_enabled", server_default=None)


def downgrade() -> None:
    product_count = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM catalog_products"))
    if product_count:
        raise RuntimeError("Cannot downgrade unified products while product data exists")

    with op.batch_alter_table("catalog_products") as batch:
        batch.drop_constraint("ck_product_fefo_requires_batch", type_="check")
        batch.drop_constraint("ck_product_expiry_requires_batch", type_="check")
        batch.drop_constraint("ck_product_issue_strategy", type_="check")
        batch.drop_constraint("ck_product_tracking_mode", type_="check")
        batch.drop_constraint("uq_catalog_products_barcode", type_="unique")
        batch.drop_constraint("uq_catalog_products_code", type_="unique")
        batch.drop_constraint("fk_catalog_products_unit", type_="foreignkey")
        batch.drop_column("quality_tracking_enabled")
        batch.drop_column("mrp_tracking_enabled")
        batch.drop_column("expiry_required")
        batch.drop_column("negative_stock_allowed")
        batch.drop_column("issue_strategy")
        batch.drop_column("tracking_mode")
        batch.drop_column("barcode")
        batch.drop_column("unit_id")
        batch.drop_column("code")

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
        sa.Column("barcode", sa.String(128), unique=True),
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
            "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')",
            name="ck_sku_issue_strategy",
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

    with op.batch_alter_table("catalog_categories") as batch:
        batch.drop_index("ix_catalog_categories_parent_name")
        batch.drop_constraint("fk_catalog_categories_parent", type_="foreignkey")
        batch.drop_column("parent_id")
