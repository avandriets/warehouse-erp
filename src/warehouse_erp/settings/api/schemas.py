from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from warehouse_erp.settings.domain.entities import SettingScope, ValueType


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class CategoryResponse(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class DefinitionCreate(BaseModel):
    category_id: UUID
    key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    value_type: ValueType
    default_value: Any = None
    allowed_scopes: tuple[SettingScope, ...]
    is_required: bool = True
    options: tuple[str, ...] = ()


class DefinitionResponse(DefinitionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class ValueUpsert(BaseModel):
    scope_type: SettingScope
    scope_id: UUID | None = None
    value: Any
    expected_version: int | None = Field(default=None, ge=1)


class ValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    definition_id: UUID
    scope_type: SettingScope
    scope_id: UUID | None
    value: Any
    version: int
    updated_at: datetime
    updated_by: UUID | None


class ResolvedResponse(BaseModel):
    key: str
    value: Any
    source_scope: SettingScope | None
    source_id: UUID | None


class InventoryDefaultsResponse(BaseModel):
    issue_strategy: str
    negative_stock_allowed: bool
    resolved_at: datetime
