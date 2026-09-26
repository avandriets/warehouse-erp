from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from warehouse_erp.warehouse.domain.entities import LocationKind


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    active: bool | None = None


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str | None
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
