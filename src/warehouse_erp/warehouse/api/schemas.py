from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from warehouse_erp.inventory.domain.policies import IssueStrategy, TrackingMode
from warehouse_erp.warehouse.domain.entities import LocationKind


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_storage_enabled: bool = False
    tracking_mode: TrackingMode = TrackingMode.NONE
    issue_strategy: IssueStrategy = IssueStrategy.MANUAL
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_storage_enabled: bool | None = None
    tracking_mode: TrackingMode | None = None
    issue_strategy: IssueStrategy | None = None

    @model_validator(mode="after")
    def reject_null_policy(self) -> "WarehouseUpdate":
        for name in ("tracking_mode", "issue_strategy", "address_storage_enabled"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    active: bool | None = None


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str | None
    address_storage_enabled: bool
    tracking_mode: TrackingMode
    issue_strategy: IssueStrategy
    active: bool
    created_at: datetime
    created_by: UUID | None
    updated_at: datetime
    updated_by: UUID | None


class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    kind: LocationKind = LocationKind.OTHER
    parent_id: UUID | None = None
    allows_stock: bool = False


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: LocationKind | None = None
    parent_id: UUID | None = None
    allows_stock: bool | None = None
    active: bool | None = None


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    warehouse_id: UUID
    parent_id: UUID | None
    code: str
    name: str
    kind: LocationKind
    allows_stock: bool
    active: bool
    created_at: datetime
    created_by: UUID | None
    updated_at: datetime
    updated_by: UUID | None
