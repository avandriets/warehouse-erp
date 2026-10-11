from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from warehouse_erp.inventory.domain.policies import (
    IssueStrategy,
    TrackingMode,
    WarehouseInventoryPolicy,
)
from warehouse_erp.shared.errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def normalize_code(value: str) -> str:
    code = value.strip().upper()
    if not code or len(code) > 64:
        raise ValidationError("Warehouse/location code must contain 1-64 characters")
    return code


def validate_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 255:
        raise ValidationError("Warehouse/location name must contain 1-255 characters")
    return name


class LocationKind(StrEnum):
    ZONE = "ZONE"
    AISLE = "AISLE"
    RACK = "RACK"
    SHELF = "SHELF"
    BIN = "BIN"
    STAGING = "STAGING"
    OTHER = "OTHER"


@dataclass(slots=True)
class Warehouse:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    address_storage_enabled: bool = False
    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code)
        self.name = validate_name(self.name)
        WarehouseInventoryPolicy(self.tracking_mode, self.issue_strategy)

    @property
    def inventory_policy(self) -> WarehouseInventoryPolicy:
        return WarehouseInventoryPolicy(self.tracking_mode, self.issue_strategy)


@dataclass(slots=True)
class Location:
    warehouse_id: UUID
    code: str
    name: str
    kind: LocationKind
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    allows_stock: bool = False
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        self.code = normalize_code(self.code)
        self.name = validate_name(self.name)
