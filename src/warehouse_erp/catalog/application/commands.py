from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from warehouse_erp.catalog.domain.entities import (
    IssueStrategy,
    MeasurementUse,
    PackageSetKind,
    TrackingMode,
    UnitDimension,
)


@dataclass(frozen=True, slots=True)
class InventoryPolicyData:
    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL
    negative_stock_allowed: bool = False
    expiry_required: bool = False
    mrp_tracking_enabled: bool = False
    quality_tracking_enabled: bool = False


@dataclass(frozen=True, slots=True)
class CreateCategory:
    code: str
    name: str
    parent_id: UUID | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCategory:
    name: str | None = None
    parent_id: UUID | None = None
    parent_id_set: bool = False
    description: str | None = None
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreateUnit:
    code: str
    name: str
    symbol: str
    dimension: UnitDimension
    precision: int = 3
    classifier_code: str | None = None
    base_unit_id: UUID | None = None
    factor_to_base: Decimal | None = None


@dataclass(frozen=True, slots=True)
class UpdateUnit:
    name: str | None = None
    symbol: str | None = None
    dimension: UnitDimension | None = None
    classifier_code: str | None = None
    classifier_code_set: bool = False
    precision: int | None = None
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreatePackageSet:
    code: str
    name: str
    kind: PackageSetKind = PackageSetKind.SHARED


@dataclass(frozen=True, slots=True)
class UpdatePackageSet:
    name: str | None = None
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreatePackage:
    package_set_id: UUID
    code: str
    name: str
    unit_id: UUID
    contains_quantity: Decimal
    contains_unit_id: UUID | None = None
    contains_package_id: UUID | None = None
    weight: Decimal | None = None
    weight_unit_id: UUID | None = None
    volume: Decimal | None = None
    volume_unit_id: UUID | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    dimension_unit_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UpdatePackage:
    name: str | None = None
    contains_quantity: Decimal | None = None
    contains_package_id: UUID | None = None
    contains_package_id_set: bool = False
    contains_unit_id: UUID | None = None
    contains_unit_id_set: bool = False
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreateProduct:
    code: str
    name: str
    category_id: UUID
    storage_unit_id: UUID
    package_set_id: UUID | None = None
    description: str | None = None
    brand: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    policy: InventoryPolicyData = field(default_factory=InventoryPolicyData)


@dataclass(frozen=True, slots=True)
class UpdateProduct:
    name: str | None = None
    category_id: UUID | None = None
    storage_unit_id: UUID | None = None
    package_set_id: UUID | None = None
    package_set_id_set: bool = False
    description: str | None = None
    brand: str | None = None
    attributes: dict[str, Any] | None = None
    policy: InventoryPolicyData | None = None
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreateProductMeasurement:
    product_id: UUID
    unit_id: UUID
    storage_quantity: Decimal
    measured_quantity: Decimal
    use: MeasurementUse = MeasurementUse.REFERENCE_ONLY
    is_report_unit: bool = False


@dataclass(frozen=True, slots=True)
class UpdateProductMeasurement:
    storage_quantity: Decimal | None = None
    measured_quantity: Decimal | None = None
    use: MeasurementUse | None = None
    is_report_unit: bool | None = None
    active: bool | None = None


@dataclass(frozen=True, slots=True)
class CreateProductBarcode:
    product_id: UUID
    value: str
    package_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UpdateProductBarcode:
    active: bool
