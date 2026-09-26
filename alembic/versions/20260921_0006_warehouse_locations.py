"""Warehouses and hierarchical locations.

Revision ID: 20260921_0006
Revises: 20260921_0005
"""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0006"
down_revision: str | None = "20260921_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id(kind: str, code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/{kind}/{code}"))


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index("ix_warehouses_active_name", "warehouses", ["active", "name"])
    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "warehouse_id",
            sa.String(36),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parent_id", sa.String(36), sa.ForeignKey("warehouse_locations.id", ondelete="RESTRICT")
        ),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("allows_stock", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),
        sa.CheckConstraint(
            "kind IN ('ZONE', 'AISLE', 'RACK', 'SHELF', 'BIN', 'STAGING', 'OTHER')",
            name="ck_warehouse_location_kind",
        ),
    )
    op.create_index(
        "ix_warehouse_locations_parent_name",
        "warehouse_locations",
        ["warehouse_id", "parent_id", "name"],
    )
    op.create_index(
        "ix_warehouse_locations_active", "warehouse_locations", ["warehouse_id", "active"]
    )

    connection = op.get_bind()
    permission_id = _id("permission", "warehouse.read")
    connection.execute(
        sa.text(
            "INSERT INTO identity_permissions (id, code, description) "
            "VALUES (:id, :code, :description)"
        ),
        {
            "id": permission_id,
            "code": "warehouse.read",
            "description": "View warehouses and locations",
        },
    )
    for role_code in ("WAREHOUSE_OPERATOR", "WAREHOUSE_MANAGER", "ADMIN"):
        connection.execute(
            sa.text(
                "INSERT INTO identity_role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id)"
            ),
            {"role_id": _id("role", role_code), "permission_id": permission_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM warehouses")):
        raise RuntimeError("Cannot downgrade warehouses while warehouse data exists")
    connection.execute(
        sa.text("DELETE FROM identity_role_permissions WHERE permission_id = :id"),
        {"id": _id("permission", "warehouse.read")},
    )
    connection.execute(
        sa.text("DELETE FROM identity_permissions WHERE id = :id"),
        {"id": _id("permission", "warehouse.read")},
    )
    op.drop_index("ix_warehouse_locations_active", table_name="warehouse_locations")
    op.drop_index("ix_warehouse_locations_parent_name", table_name="warehouse_locations")
    op.drop_table("warehouse_locations")
    op.drop_index("ix_warehouses_active_name", table_name="warehouses")
    op.drop_table("warehouses")
