from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from warehouse_erp.database import Base


class CategoryModel(Base):
    __tablename__ = "catalog_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_categories.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_catalog_categories_active_name", "active", "name"),
        Index("ix_catalog_categories_parent_name", "parent_id", "name"),
    )


class UnitModel(Base):
    __tablename__ = "catalog_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    classifier_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    base_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT")
    )
    factor_to_base: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "`precision` >= 0 AND `precision` <= 6",
            name="ck_catalog_unit_precision",
        ),
        CheckConstraint(
            "dimension IN ('COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'OTHER')",
            name="ck_catalog_unit_dimension",
        ),
        CheckConstraint(
            "factor_to_base IS NULL OR factor_to_base > 0", name="ck_catalog_unit_factor_positive"
        ),
    )


class PackageSetModel(Base):
    __tablename__ = "catalog_package_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('SHARED', 'INDIVIDUAL')", name="ck_package_set_kind"),
    )


class PackageModel(Base):
    __tablename__ = "catalog_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_package_sets.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT"), nullable=False
    )
    contains_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_packages.id", ondelete="RESTRICT")
    )
    contains_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT")
    )
    contains_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 9), nullable=False)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    weight_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT")
    )
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    volume_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT")
    )
    length: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    width: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    height: Mapped[Decimal | None] = mapped_column(Numeric(24, 9))
    dimension_unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("package_set_id", "code", name="uq_catalog_package_set_code"),
        CheckConstraint("contains_quantity > 0", name="ck_package_contains_positive"),
        CheckConstraint(
            "(contains_unit_id IS NULL AND contains_package_id IS NOT NULL) OR "
            "(contains_unit_id IS NOT NULL AND contains_package_id IS NULL)",
            name="ck_package_contains_one_target",
        ),
        Index("ix_catalog_packages_set_active", "package_set_id", "active"),
    )


class ProductModel(Base):
    __tablename__ = "catalog_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_categories.id", ondelete="RESTRICT"), nullable=False
    )
    storage_unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT"), nullable=False
    )
    package_set_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_package_sets.id", ondelete="RESTRICT")
    )
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    tracking_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    issue_strategy: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    negative_stock_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expiry_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mrp_tracking_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_tracking_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_catalog_products_code"),
        CheckConstraint("tracking_mode IN ('NONE', 'BATCH')", name="ck_product_tracking_mode"),
        CheckConstraint(
            "issue_strategy IN ('MANUAL', 'FIFO', 'FEFO')",
            name="ck_product_issue_strategy",
        ),
        CheckConstraint(
            "expiry_required = false OR tracking_mode = 'BATCH'",
            name="ck_product_expiry_requires_batch",
        ),
        CheckConstraint(
            "issue_strategy != 'FEFO' OR tracking_mode = 'BATCH'",
            name="ck_product_fefo_requires_batch",
        ),
        Index("ix_catalog_products_category_active", "category_id", "active"),
        Index("ix_catalog_products_name", "name"),
    )


class ProductMeasurementModel(Base):
    __tablename__ = "catalog_product_measurements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_products.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_units.id", ondelete="RESTRICT"), nullable=False
    )
    storage_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 9), nullable=False)
    measured_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 9), nullable=False)
    use: Mapped[str] = mapped_column(String(24), nullable=False)
    is_report_unit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "unit_id", name="uq_product_measurement_unit"),
        CheckConstraint("storage_quantity > 0", name="ck_measurement_storage_positive"),
        CheckConstraint("measured_quantity > 0", name="ck_measurement_measured_positive"),
        CheckConstraint(
            "`use` IN ('REFERENCE_ONLY', 'DOCUMENT')", name="ck_product_measurement_use"
        ),
        Index("ix_product_measurements_product_active", "product_id", "active"),
    )


class ProductBarcodeModel(Base):
    __tablename__ = "catalog_product_barcodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("catalog_products.id", ondelete="RESTRICT"), nullable=False
    )
    package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalog_packages.id", ondelete="RESTRICT")
    )
    value: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_product_barcodes_product_active", "product_id", "active"),)
