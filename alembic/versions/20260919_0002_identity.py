"""Create identity and authorization tables.

Revision ID: 20260919_0002
Revises: 20260918_0001
Create Date: 2026-09-19
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0002"
down_revision: str | None = "20260918_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "catalog.read": "View catalog records",
    "catalog.create": "Create catalog records",
    "catalog.edit": "Edit and deactivate catalog records",
    "inventory.read": "View inventory documents, balances, and ledger",
    "inventory.document.create": "Create stock-affecting documents",
    "inventory.document.edit": "Edit draft stock-affecting documents",
    "inventory.document.post": "Post stock-affecting documents",
    "inventory.document.reverse": "Reverse posted stock-affecting documents",
    "inventory.adjust": "Create and post inventory adjustments",
    "inventory.period.close": "Close inventory accounting periods",
    "warehouse.manage": "Manage warehouses and locations",
    "settings.manage": "Manage application settings",
    "users.manage": "Manage users, roles, and role assignments",
}

ROLES = {
    "WAREHOUSE_OPERATOR": {
        "name": "Warehouse operator",
        "description": "Creates and edits warehouse documents without posting them.",
        "permissions": {
            "catalog.read",
            "inventory.read",
            "inventory.document.create",
            "inventory.document.edit",
        },
    },
    "WAREHOUSE_MANAGER": {
        "name": "Warehouse manager",
        "description": "Posts warehouse documents and manages stock control operations.",
        "permissions": {
            "catalog.read",
            "inventory.read",
            "inventory.document.create",
            "inventory.document.edit",
            "inventory.document.post",
            "inventory.document.reverse",
            "inventory.adjust",
            "warehouse.manage",
        },
    },
    "ADMIN": {
        "name": "Administrator",
        "description": "Full access to all Warehouse ERP permissions.",
        "permissions": set(PERMISSIONS),
    },
}


def _permission_id(code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/permission/{code}"))


def _role_id(code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/role/{code}"))


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("auth0_subject", sa.String(255), unique=True),
        sa.Column("email", sa.String(320), unique=True),
        sa.Column("display_name", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="SET NULL"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint(
            "status IN ('INVITED', 'PENDING_APPROVAL', 'ACTIVE', 'SUSPENDED')",
            name="ck_identity_user_status",
        ),
    )
    op.create_index("ix_identity_users_status", "identity_users", ["status"])

    permissions = op.create_table(
        "identity_permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=False),
    )
    roles = op.create_table(
        "identity_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("system_role", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="SET NULL"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_identity_roles_active_name", "identity_roles", ["active", "name"])

    role_permissions = op.create_table(
        "identity_role_permissions",
        sa.Column(
            "role_id",
            sa.String(36),
            sa.ForeignKey("identity_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.String(36),
            sa.ForeignKey("identity_permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "identity_role_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.String(36),
            sa.ForeignKey("identity_roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(36)),
        sa.Column("scope_key", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("identity_users.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint(
            "scope_type IN ('GLOBAL', 'COMPANY', 'WAREHOUSE')",
            name="ck_identity_assignment_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(scope_type != 'GLOBAL' AND scope_id IS NOT NULL AND scope_key = scope_id)",
            name="ck_identity_assignment_scope",
        ),
        sa.UniqueConstraint(
            "user_id",
            "role_id",
            "scope_type",
            "scope_key",
            name="uq_identity_assignment_target",
        ),
    )
    op.create_index(
        "ix_identity_assignments_user",
        "identity_role_assignments",
        ["user_id"],
    )

    now = datetime.now(UTC)
    op.bulk_insert(
        permissions,
        [
            {"id": _permission_id(code), "code": code, "description": description}
            for code, description in PERMISSIONS.items()
        ],
    )
    op.bulk_insert(
        roles,
        [
            {
                "id": _role_id(code),
                "code": code,
                "name": definition["name"],
                "description": definition["description"],
                "active": True,
                "system_role": True,
                "created_at": now,
                "updated_at": now,
            }
            for code, definition in ROLES.items()
        ],
    )
    op.bulk_insert(
        role_permissions,
        [
            {
                "role_id": _role_id(code),
                "permission_id": _permission_id(permission_code),
            }
            for code, definition in ROLES.items()
            for permission_code in definition["permissions"]
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_assignments_user", table_name="identity_role_assignments")
    op.drop_table("identity_role_assignments")
    op.drop_table("identity_role_permissions")
    op.drop_index("ix_identity_roles_active_name", table_name="identity_roles")
    op.drop_table("identity_roles")
    op.drop_table("identity_permissions")
    op.drop_index("ix_identity_users_status", table_name="identity_users")
    op.drop_table("identity_users")
