"""Add dimensional units, package hierarchies, and product measurements.

Revision ID: 20260921_0004
Revises: 20260920_0003
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0004"
down_revision: str | None = "20260920_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("catalog_units") as batch:
        batch.add_column(sa.Column("symbol", sa.String(32), nullable=True))
        batch.add_column(
            sa.Column("dimension", sa.String(16), nullable=False, server_default="OTHER")
        )
        batch.add_column(sa.Column("classifier_code", sa.String(32), nullable=True))
        batch.add_column(sa.Column("base_unit_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("factor_to_base", sa.Numeric(24, 9), nullable=True))
        batch.create_foreign_key(
            "fk_catalog_units_base", "catalog_units", ["base_unit_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_check_constraint(
            "ck_catalog_unit_factor_positive", "factor_to_base IS NULL OR factor_to_base > 0"
        )
        batch.create_unique_constraint("uq_catalog_units_classifier_code", ["classifier_code"])
        batch.create_check_constraint(
            "ck_catalog_unit_dimension",
            "dimension IN ('COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'OTHER')",
        )
    op.execute(sa.text("UPDATE catalog_units SET symbol = code"))
    with op.batch_alter_table("catalog_units") as batch:
        batch.alter_column("symbol", existing_type=sa.String(32), nullable=False)
        batch.alter_column("dimension", server_default=None)

    op.create_table(
        "catalog_package_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('SHARED', 'INDIVIDUAL')", name="ck_package_set_kind"),
    )
    op.create_table(
        "catalog_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "package_set_id",
            sa.String(36),
            sa.ForeignKey("catalog_package_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "unit_id",
            sa.String(36),
            sa.ForeignKey("catalog_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "contains_package_id",
            sa.String(36),
            sa.ForeignKey("catalog_packages.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "contains_unit_id",
            sa.String(36),
            sa.ForeignKey("catalog_units.id", ondelete="RESTRICT"),
        ),
        sa.Column("contains_quantity", sa.Numeric(24, 9), nullable=False),
        sa.Column("weight", sa.Numeric(24, 9)),
        sa.Column(
            "weight_unit_id", sa.String(36), sa.ForeignKey("catalog_units.id", ondelete="RESTRICT")
        ),
        sa.Column("volume", sa.Numeric(24, 9)),
        sa.Column(
            "volume_unit_id", sa.String(36), sa.ForeignKey("catalog_units.id", ondelete="RESTRICT")
        ),
        sa.Column("length", sa.Numeric(24, 9)),
        sa.Column("width", sa.Numeric(24, 9)),
        sa.Column("height", sa.Numeric(24, 9)),
        sa.Column(
            "dimension_unit_id",
            sa.String(36),
            sa.ForeignKey("catalog_units.id", ondelete="RESTRICT"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("package_set_id", "code", name="uq_catalog_package_set_code"),
        sa.CheckConstraint("contains_quantity > 0", name="ck_package_contains_positive"),
        sa.CheckConstraint(
            "(contains_unit_id IS NULL AND contains_package_id IS NOT NULL) OR "
            "(contains_unit_id IS NOT NULL AND contains_package_id IS NULL)",
            name="ck_package_contains_one_target",
        ),
    )
    op.create_index(
        "ix_catalog_packages_set_active", "catalog_packages", ["package_set_id", "active"]
    )

    with op.batch_alter_table("catalog_products") as batch:
        batch.alter_column(
            "unit_id",
            new_column_name="storage_unit_id",
            existing_type=sa.String(36),
            existing_nullable=False,
        )
        batch.add_column(sa.Column("package_set_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_catalog_products_package_set",
            "catalog_package_sets",
            ["package_set_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "catalog_product_measurements",
        sa.Column("id", sa.String(36), primary_key=True),
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
        sa.Column("storage_quantity", sa.Numeric(24, 9), nullable=False),
        sa.Column("measured_quantity", sa.Numeric(24, 9), nullable=False),
        sa.Column("use", sa.String(24), nullable=False),
        sa.Column("is_report_unit", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "unit_id", name="uq_product_measurement_unit"),
        sa.CheckConstraint("storage_quantity > 0", name="ck_measurement_storage_positive"),
        sa.CheckConstraint("measured_quantity > 0", name="ck_measurement_measured_positive"),
        sa.CheckConstraint(
            "`use` IN ('REFERENCE_ONLY', 'DOCUMENT')", name="ck_product_measurement_use"
        ),
    )
    op.create_index(
        "ix_product_measurements_product_active",
        "catalog_product_measurements",
        ["product_id", "active"],
    )
    op.create_table(
        "catalog_product_barcodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "product_id",
            sa.String(36),
            sa.ForeignKey("catalog_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "package_id", sa.String(36), sa.ForeignKey("catalog_packages.id", ondelete="RESTRICT")
        ),
        sa.Column("value", sa.String(128), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_product_barcodes_product_active", "catalog_product_barcodes", ["product_id", "active"]
    )

    connection = op.get_bind()
    barcodes = sa.table(
        "catalog_product_barcodes",
        sa.column("id", sa.String),
        sa.column("product_id", sa.String),
        sa.column("value", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    rows = connection.execute(
        sa.text(
            "SELECT id, barcode, created_at, updated_at "
            "FROM catalog_products WHERE barcode IS NOT NULL"
        )
    )
    for row in rows:
        created_at = (
            datetime.fromisoformat(row.created_at)
            if isinstance(row.created_at, str)
            else row.created_at
        )
        updated_at = (
            datetime.fromisoformat(row.updated_at)
            if isinstance(row.updated_at, str)
            else row.updated_at
        )
        connection.execute(
            barcodes.insert().values(
                id=str(uuid4()),
                product_id=row.id,
                value=row.barcode,
                active=True,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
    with op.batch_alter_table("catalog_products") as batch:
        batch.drop_constraint("uq_catalog_products_barcode", type_="unique")
        batch.drop_column("barcode")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM catalog_packages")) or connection.scalar(
        sa.text("SELECT COUNT(*) FROM catalog_product_measurements")
    ):
        raise RuntimeError("Cannot downgrade while packages or measurements exist")
    if connection.scalar(
        sa.text("SELECT COUNT(*) FROM catalog_product_barcodes WHERE package_id IS NOT NULL")
    ):
        raise RuntimeError("Cannot downgrade package barcodes")
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT product_id FROM catalog_product_barcodes "
            "GROUP BY product_id HAVING COUNT(*) > 1) t"
        )
    ):
        raise RuntimeError("Cannot downgrade multiple barcodes per product")
    with op.batch_alter_table("catalog_products") as batch:
        batch.add_column(sa.Column("barcode", sa.String(128)))
        batch.create_unique_constraint("uq_catalog_products_barcode", ["barcode"])
    for row in connection.execute(
        sa.text("SELECT product_id, value FROM catalog_product_barcodes")
    ):
        connection.execute(
            sa.text("UPDATE catalog_products SET barcode = :value WHERE id = :id"),
            {"value": row.value, "id": row.product_id},
        )
    op.drop_index("ix_product_barcodes_product_active", table_name="catalog_product_barcodes")
    op.drop_table("catalog_product_barcodes")
    op.drop_index(
        "ix_product_measurements_product_active", table_name="catalog_product_measurements"
    )
    op.drop_table("catalog_product_measurements")
    with op.batch_alter_table("catalog_products") as batch:
        batch.drop_constraint("fk_catalog_products_package_set", type_="foreignkey")
        batch.drop_column("package_set_id")
        batch.alter_column(
            "storage_unit_id",
            new_column_name="unit_id",
            existing_type=sa.String(36),
            existing_nullable=False,
        )
    op.drop_index("ix_catalog_packages_set_active", table_name="catalog_packages")
    op.drop_table("catalog_packages")
    op.drop_table("catalog_package_sets")
    with op.batch_alter_table("catalog_units") as batch:
        batch.drop_constraint("ck_catalog_unit_factor_positive", type_="check")
        batch.drop_constraint("fk_catalog_units_base", type_="foreignkey")
        batch.drop_column("factor_to_base")
        batch.drop_column("base_unit_id")
        batch.drop_constraint("ck_catalog_unit_dimension", type_="check")
        batch.drop_constraint("uq_catalog_units_classifier_code", type_="unique")
        batch.drop_column("classifier_code")
        batch.drop_column("dimension")
        batch.drop_column("symbol")
