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


class WarehouseModel(Base):
    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (Index("ix_warehouses_active_name", "active", "name"),)


class LocationModel(Base):
    __tablename__ = "warehouse_locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("warehouse_locations.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    allows_stock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),
        CheckConstraint(
            "kind IN ('ZONE', 'AISLE', 'RACK', 'SHELF', 'BIN', 'STAGING', 'OTHER')",
            name="ck_warehouse_location_kind",
        ),
        Index("ix_warehouse_locations_parent_name", "warehouse_id", "parent_id", "name"),
        Index("ix_warehouse_locations_active", "warehouse_id", "active"),
    )
