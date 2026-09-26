"""Typed scoped settings and initial inventory defaults.

Revision ID: 20260921_0005
Revises: 20260921_0004
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0005"
down_revision: str | None = "20260921_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id(kind: str, code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/{kind}/{code}"))


def upgrade() -> None:
    categories = op.create_table(
        "settings_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    definitions = op.create_table(
        "settings_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "category_id",
            sa.String(36),
            sa.ForeignKey("settings_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("default_value", sa.JSON()),
        sa.Column("allowed_scopes", sa.JSON(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value_type IN ('BOOLEAN', 'INTEGER', 'DECIMAL', 'STRING', 'ENUM')",
            name="ck_settings_definition_type",
        ),
    )
    op.create_index("ix_settings_definitions_category", "settings_definitions", ["category_id"])
    op.create_table(
        "settings_values",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "definition_id",
            sa.String(36),
            sa.ForeignKey("settings_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(36)),
        sa.Column("scope_key", sa.String(36), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_type IN ('GLOBAL', 'COMPANY', 'WAREHOUSE', 'CATEGORY', 'PRODUCT')",
            name="ck_settings_value_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(scope_type != 'GLOBAL' AND scope_id IS NOT NULL AND scope_key = scope_id)",
            name="ck_settings_value_scope",
        ),
        sa.CheckConstraint("version >= 1", name="ck_settings_value_version"),
        sa.UniqueConstraint(
            "definition_id", "scope_type", "scope_key", name="uq_settings_value_target"
        ),
    )
    op.create_index(
        "ix_settings_values_lookup", "settings_values", ["definition_id", "scope_type", "scope_key"]
    )

    now = datetime.now(UTC)
    category_id = _id("settings-category", "inventory")
    op.bulk_insert(
        categories,
        [
            {
                "id": category_id,
                "code": "inventory",
                "name": "Inventory",
                "created_at": now,
            }
        ],
    )
    scopes = ["GLOBAL", "COMPANY", "WAREHOUSE", "CATEGORY", "PRODUCT"]
    op.bulk_insert(
        definitions,
        [
            {
                "id": _id("setting", "inventory.default_issue_strategy"),
                "category_id": category_id,
                "key": "inventory.default_issue_strategy",
                "name": "Default stock issue strategy",
                "value_type": "ENUM",
                "default_value": "MANUAL",
                "allowed_scopes": scopes,
                "is_required": True,
                "options": ["MANUAL", "FIFO", "FEFO"],
                "created_at": now,
            },
            {
                "id": _id("setting", "inventory.negative_stock_allowed"),
                "category_id": category_id,
                "key": "inventory.negative_stock_allowed",
                "name": "Allow negative stock by default",
                "value_type": "BOOLEAN",
                "default_value": False,
                "allowed_scopes": scopes,
                "is_required": True,
                "options": [],
                "created_at": now,
            },
        ],
    )
    connection = op.get_bind()
    permission_code = "settings.read"
    connection.execute(
        sa.text(
            "INSERT INTO identity_permissions (id, code, description) "
            "VALUES (:id, :code, :description)"
        ),
        {
            "id": _id("permission", permission_code),
            "code": permission_code,
            "description": "View settings and resolved values",
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO identity_role_permissions (role_id, permission_id) "
            "VALUES (:role_id, :permission_id)"
        ),
        {"role_id": _id("role", "ADMIN"), "permission_id": _id("permission", permission_code)},
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM settings_values")):
        raise RuntimeError("Cannot downgrade settings while overrides exist")
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM settings_definitions WHERE `key` NOT IN "
            "('inventory.default_issue_strategy', 'inventory.negative_stock_allowed')"
        )
    ):
        raise RuntimeError("Cannot downgrade settings while custom definitions exist")
    connection.execute(
        sa.text("DELETE FROM identity_role_permissions WHERE permission_id = :id"),
        {"id": _id("permission", "settings.read")},
    )
    connection.execute(
        sa.text("DELETE FROM identity_permissions WHERE id = :id"),
        {"id": _id("permission", "settings.read")},
    )
    op.drop_table("settings_values")
    op.drop_table("settings_definitions")
    op.drop_table("settings_categories")
