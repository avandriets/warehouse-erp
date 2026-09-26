from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from warehouse_erp.shared.errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def normalize_code(value: str, field_name: str = "code") -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty")
    if len(normalized) > 64:
        raise ValidationError(f"{field_name} must not exceed 64 characters")
    return normalized


def validate_name(value: str, field_name: str = "name") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty")
    if len(normalized) > 255:
        raise ValidationError(f"{field_name} must not exceed 255 characters")
    return normalized


class TrackingMode(StrEnum):
    NONE = "NONE"
    BATCH = "BATCH"


class IssueStrategy(StrEnum):
    MANUAL = "MANUAL"
    FIFO = "FIFO"
    FEFO = "FEFO"


class UnitDimension(StrEnum):
    COUNT = "COUNT"
    MASS = "MASS"
    VOLUME = "VOLUME"
    LENGTH = "LENGTH"
    AREA = "AREA"
    OTHER = "OTHER"


class PackageSetKind(StrEnum):
    SHARED = "SHARED"
    INDIVIDUAL = "INDIVIDUAL"


class MeasurementUse(StrEnum):
    REFERENCE_ONLY = "REFERENCE_ONLY"
    DOCUMENT = "DOCUMENT"


@dataclass(frozen=True, slots=True)
class ProductInventoryPolicy:
    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL
    negative_stock_allowed: bool = False
    expiry_required: bool = False
    mrp_tracking_enabled: bool = False
    quality_tracking_enabled: bool = False

    def __post_init__(self) -> None:
        if self.expiry_required and self.tracking_mode is not TrackingMode.BATCH:
            raise ValidationError("expiry_required can only be enabled for batch-tracked products")
        if (
            self.issue_strategy is IssueStrategy.FEFO
            and self.tracking_mode is not TrackingMode.BATCH
        ):
            raise ValidationError("FEFO can only be used for batch-tracked products")


@dataclass(slots=True)
class Category:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    description: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code)
        self.name = validate_name(self.name)


@dataclass(slots=True)
class Unit:
    code: str
    name: str
    symbol: str
    dimension: UnitDimension
    precision: int = 3
    id: UUID = field(default_factory=uuid4)
    classifier_code: str | None = None
    base_unit_id: UUID | None = None
    factor_to_base: Decimal | None = None
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code)
        self.name = validate_name(self.name)
        self.symbol = self.symbol.strip()
        if not self.symbol:
            raise ValidationError("unit symbol must not be empty")
        if len(self.symbol) > 32:
            raise ValidationError("unit symbol must not exceed 32 characters")
        if self.classifier_code is not None:
            self.classifier_code = self.classifier_code.strip() or None
        if not 0 <= self.precision <= 6:
            raise ValidationError("precision must be between 0 and 6")
        if (self.base_unit_id is None) != (self.factor_to_base is None):
            raise ValidationError("base_unit_id and factor_to_base must be specified together")
        _positive_decimal(self.factor_to_base, "factor_to_base")


@dataclass(slots=True)
class PackageSet:
    code: str
    name: str
    kind: PackageSetKind = PackageSetKind.SHARED
    id: UUID = field(default_factory=uuid4)
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code, "package set code")
        self.name = validate_name(self.name, "package set name")


def _positive_decimal(value: Decimal | None, field_name: str) -> None:
    if value is not None and value <= 0:
        raise ValidationError(f"{field_name} must be greater than zero")


@dataclass(slots=True)
class Package:
    package_set_id: UUID
    code: str
    name: str
    unit_id: UUID
    contains_quantity: Decimal
    contains_unit_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    contains_package_id: UUID | None = None
    weight: Decimal | None = None
    weight_unit_id: UUID | None = None
    volume: Decimal | None = None
    volume_unit_id: UUID | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    dimension_unit_id: UUID | None = None
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code, "package code")
        self.name = validate_name(self.name, "package name")
        _positive_decimal(self.contains_quantity, "contains_quantity")
        if (self.contains_unit_id is None) == (self.contains_package_id is None):
            raise ValidationError("Package must contain either a unit or another package")
        _positive_decimal(self.weight, "weight")
        _positive_decimal(self.volume, "volume")
        for field_name in ("length", "width", "height"):
            _positive_decimal(getattr(self, field_name), field_name)
        if (self.weight is None) != (self.weight_unit_id is None):
            raise ValidationError("weight and weight_unit_id must be specified together")
        if (self.volume is None) != (self.volume_unit_id is None):
            raise ValidationError("volume and volume_unit_id must be specified together")
        dimensions = (self.length, self.width, self.height)
        if any(value is not None for value in dimensions):
            if not all(value is not None for value in dimensions) or self.dimension_unit_id is None:
                raise ValidationError(
                    "length, width, height and dimension_unit_id must be specified together"
                )
        elif self.dimension_unit_id is not None:
            raise ValidationError("dimension_unit_id requires length, width and height")


@dataclass(slots=True)
class ProductMeasurement:
    product_id: UUID
    unit_id: UUID
    storage_quantity: Decimal
    measured_quantity: Decimal
    use: MeasurementUse = MeasurementUse.REFERENCE_ONLY
    id: UUID = field(default_factory=uuid4)
    is_report_unit: bool = False
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _positive_decimal(self.storage_quantity, "storage_quantity")
        _positive_decimal(self.measured_quantity, "measured_quantity")

    def to_storage_quantity(self, quantity: Decimal) -> Decimal:
        return quantity * self.storage_quantity / self.measured_quantity


@dataclass(slots=True)
class ProductBarcode:
    product_id: UUID
    value: str
    id: UUID = field(default_factory=uuid4)
    package_id: UUID | None = None
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.value = self.value.strip()
        if not self.value:
            raise ValidationError("barcode must not be empty")
        if len(self.value) > 128:
            raise ValidationError("barcode must not exceed 128 characters")


@dataclass(slots=True)
class Product:
    code: str
    name: str
    category_id: UUID
    storage_unit_id: UUID
    policy: ProductInventoryPolicy = field(default_factory=ProductInventoryPolicy)
    id: UUID = field(default_factory=uuid4)
    package_set_id: UUID | None = None
    description: str | None = None
    brand: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code, "product code")
        self.name = validate_name(self.name, "product name")
        if self.brand is not None:
            self.brand = self.brand.strip() or None
