from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from warehouse_erp.database import Base


class UserModel(Base):
    __tablename__ = "identity_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auth0_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('INVITED', 'PENDING_APPROVAL', 'ACTIVE', 'SUSPENDED')",
            name="ck_identity_user_status",
        ),
        Index("ix_identity_users_status", "status"),
    )


class PermissionModel(Base):
    __tablename__ = "identity_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class RoleModel(Base):
    __tablename__ = "identity_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_identity_roles_active_name", "active", "name"),)


class RolePermissionModel(Base):
    __tablename__ = "identity_role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("identity_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("identity_permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class RoleAssignmentModel(Base):
    __tablename__ = "identity_role_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_roles.id", ondelete="RESTRICT"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(36))
    scope_key: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('GLOBAL', 'COMPANY', 'WAREHOUSE')",
            name="ck_identity_assignment_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL AND scope_key = 'GLOBAL') OR "
            "(scope_type != 'GLOBAL' AND scope_id IS NOT NULL AND scope_key = scope_id)",
            name="ck_identity_assignment_scope",
        ),
        UniqueConstraint(
            "user_id",
            "role_id",
            "scope_type",
            "scope_key",
            name="uq_identity_assignment_target",
        ),
        Index("ix_identity_assignments_user", "user_id"),
    )
