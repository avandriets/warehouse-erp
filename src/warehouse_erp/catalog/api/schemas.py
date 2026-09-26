from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from warehouse_erp.catalog.domain.entities import (
    IssueStrategy,
    MeasurementUse,
    PackageSetKind,
    TrackingMode,
    UnitDimension,
)


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: UUID | None = None
    description: str | None = None
    active: bool | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None
    code: str
    name: str
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class UnitCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    symbol: str = Field(min_length=1, max_length=32)
    dimension: UnitDimension
    precision: int = Field(default=3, ge=0, le=6)
    classifier_code: str | None = Field(default=None, max_length=32)
    base_unit_id: UUID | None = None
    factor_to_base: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    dimension: UnitDimension | None = None
    classifier_code: str | None = Field(default=None, max_length=32)
    precision: int | None = Field(default=None, ge=0, le=6)
    active: bool | None = None


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    symbol: str
    dimension: UnitDimension
    classifier_code: str | None
    base_unit_id: UUID | None
    factor_to_base: Decimal | None
    precision: int
    active: bool
    created_at: datetime
    updated_at: datetime


class PackageSetCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    kind: PackageSetKind = PackageSetKind.SHARED


class PackageSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None


class PackageSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    kind: PackageSetKind
    active: bool
    created_at: datetime
    updated_at: datetime


class PackageCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_id: UUID
    contains_quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=9)
    contains_unit_id: UUID | None = None
    contains_package_id: UUID | None = None
    weight: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    weight_unit_id: UUID | None = None
    volume: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    volume_unit_id: UUID | None = None
    length: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    width: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    height: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    dimension_unit_id: UUID | None = None


class PackageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contains_quantity: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    contains_package_id: UUID | None = None
    contains_unit_id: UUID | None = None
    active: bool | None = None


class PackageResponse(PackageCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    package_set_id: UUID
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductMeasurementCreate(BaseModel):
    unit_id: UUID
    storage_quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=9)
    measured_quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=9)
    use: MeasurementUse = MeasurementUse.REFERENCE_ONLY
    is_report_unit: bool = False


class ProductMeasurementUpdate(BaseModel):
    storage_quantity: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    measured_quantity: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=9)
    use: MeasurementUse | None = None
    is_report_unit: bool | None = None
    active: bool | None = None


class ProductMeasurementResponse(ProductMeasurementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductBarcodeCreate(BaseModel):
    value: str = Field(min_length=1, max_length=128)
    package_id: UUID | None = None


class ProductBarcodeUpdate(BaseModel):
    active: bool


class ProductBarcodeResponse(ProductBarcodeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductConversionRequest(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=9)
    package_id: UUID | None = None
    measurement_id: UUID | None = None


class ProductConversionResponse(BaseModel):
    storage_unit_id: UUID
    storage_quantity: Decimal
    factor: Decimal


class UnitConversionRequest(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=9)
    from_unit_id: UUID
    to_unit_id: UUID


class UnitConversionResponse(BaseModel):
    quantity: Decimal
    unit_id: UUID


class InventoryPolicySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL
    negative_stock_allowed: bool = False
    expiry_required: bool = False
    mrp_tracking_enabled: bool = False
    quality_tracking_enabled: bool = False


class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category_id: UUID
    storage_unit_id: UUID
    package_set_id: UUID | None = None
    description: str | None = None
    brand: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    policy: InventoryPolicySchema = Field(default_factory=InventoryPolicySchema)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: UUID | None = None
    storage_unit_id: UUID | None = None
    package_set_id: UUID | None = None
    description: str | None = None
    brand: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] | None = None
    policy: InventoryPolicySchema | None = None
    active: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    category_id: UUID
    storage_unit_id: UUID
    package_set_id: UUID | None
    description: str | None
    brand: str | None
    attributes: dict[str, Any]
    policy: InventoryPolicySchema
    active: bool
    created_at: datetime
    updated_at: datetime
