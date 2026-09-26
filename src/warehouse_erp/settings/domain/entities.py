from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from warehouse_erp.shared.errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def validate_code(value: str) -> str:
    code = value.strip().lower()
    if not code or len(code) > 128 or not all(c.isalnum() or c in "._-" for c in code):
        raise ValidationError("setting code is invalid")
    return code


class ValueType(StrEnum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    STRING = "STRING"
    ENUM = "ENUM"


class SettingScope(StrEnum):
    GLOBAL = "GLOBAL"
    COMPANY = "COMPANY"
    WAREHOUSE = "WAREHOUSE"
    CATEGORY = "CATEGORY"
    PRODUCT = "PRODUCT"


def canonical_value(value: Any, value_type: ValueType, options: tuple[str, ...] = ()) -> Any:
    if value_type is ValueType.BOOLEAN:
        if type(value) is not bool:
            raise ValidationError("Setting value must be boolean")
        return value
    if value_type is ValueType.INTEGER:
        if type(value) is not int:
            raise ValidationError("Setting value must be integer")
        return value
    if value_type is ValueType.DECIMAL:
        if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
            raise ValidationError("Setting value must be decimal")
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValidationError("Setting value must be decimal") from exc
        if not number.is_finite():
            raise ValidationError("Setting decimal must be finite")
        return str(number)
    if not isinstance(value, str):
        raise ValidationError("Setting value must be string")
    if value_type is ValueType.ENUM and value not in options:
        raise ValidationError("Setting value is not an allowed option")
    if len(value) > 1024:
        raise ValidationError("Setting string must not exceed 1024 characters")
    return value


@dataclass(slots=True)
class SettingsCategory:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.code = validate_code(self.code)
        self.name = self.name.strip()
        if not self.name or len(self.name) > 255:
            raise ValidationError("Settings category name is invalid")


@dataclass(slots=True)
class SettingDefinition:
    category_id: UUID
    key: str
    name: str
    value_type: ValueType
    default_value: Any
    allowed_scopes: tuple[SettingScope, ...]
    id: UUID = field(default_factory=uuid4)
    is_required: bool = True
    options: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.key = validate_code(self.key)
        self.name = self.name.strip()
        if not self.name or len(self.name) > 255:
            raise ValidationError("Setting name is invalid")
        if not self.allowed_scopes or len(set(self.allowed_scopes)) != len(self.allowed_scopes):
            raise ValidationError("allowed_scopes must be nonempty and unique")
        if self.value_type is ValueType.ENUM:
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValidationError("ENUM settings require unique options")
        elif self.options:
            raise ValidationError("options are only supported for ENUM settings")
        if self.default_value is None and self.is_required:
            raise ValidationError("Required setting needs a default value")
        if self.default_value is not None:
            self.default_value = canonical_value(self.default_value, self.value_type, self.options)


@dataclass(slots=True)
class SettingValue:
    definition_id: UUID
    scope_type: SettingScope
    scope_id: UUID | None
    value: Any
    id: UUID = field(default_factory=uuid4)
    version: int = 1
    updated_at: datetime = field(default_factory=utc_now)
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope_type is SettingScope.GLOBAL and self.scope_id is not None:
            raise ValidationError("GLOBAL setting must not have scope_id")
        if self.scope_type is not SettingScope.GLOBAL and self.scope_id is None:
            raise ValidationError("Scoped setting requires scope_id")

    @property
    def scope_key(self) -> str:
        return "GLOBAL" if self.scope_id is None else str(self.scope_id)


@dataclass(frozen=True, slots=True)
class SettingsContext:
    company_id: UUID | None = None
    warehouse_id: UUID | None = None
    category_id: UUID | None = None
    product_id: UUID | None = None

    def candidates(self) -> tuple[tuple[SettingScope, UUID | None], ...]:
        items = (
            (SettingScope.PRODUCT, self.product_id),
            (SettingScope.CATEGORY, self.category_id),
            (SettingScope.WAREHOUSE, self.warehouse_id),
            (SettingScope.COMPANY, self.company_id),
        )
        return tuple((scope, scope_id) for scope, scope_id in items if scope_id is not None) + (
            (SettingScope.GLOBAL, None),
        )


@dataclass(frozen=True, slots=True)
class ResolvedSetting:
    key: str
    value: Any
    source_scope: SettingScope | None
    source_id: UUID | None
