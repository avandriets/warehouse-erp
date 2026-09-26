from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from time import monotonic
from typing import Any
from uuid import UUID

from warehouse_erp.settings.domain.entities import (
    ResolvedSetting,
    SettingDefinition,
    SettingsCategory,
    SettingsContext,
    SettingScope,
    SettingValue,
    ValueType,
    canonical_value,
    utc_now,
    validate_code,
)
from warehouse_erp.settings.domain.repositories import SettingsUnitOfWork
from warehouse_erp.shared.errors import ConflictError, NotFoundError, ValidationError


class SettingsKey(StrEnum):
    DEFAULT_ISSUE_STRATEGY = "inventory.default_issue_strategy"
    NEGATIVE_STOCK_ALLOWED = "inventory.negative_stock_allowed"


class InventoryIssueStrategy(StrEnum):
    MANUAL = "MANUAL"
    FIFO = "FIFO"
    FEFO = "FEFO"


@dataclass(frozen=True, slots=True)
class InventoryDefaults:
    issue_strategy: InventoryIssueStrategy
    negative_stock_allowed: bool
    resolved_at: datetime


class InventoryDefaultsCache:
    def __init__(self, ttl_seconds: float = 15.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[SettingsContext, tuple[float, InventoryDefaults]] = {}
        self._lock = RLock()

    def get(self, context: SettingsContext) -> InventoryDefaults | None:
        with self._lock:
            entry = self._items.get(context)
            if entry is None:
                return None
            expires_at, snapshot = entry
            if monotonic() >= expires_at:
                del self._items[context]
                return None
            return snapshot

    def put(self, context: SettingsContext, snapshot: InventoryDefaults) -> None:
        with self._lock:
            self._items[context] = (monotonic() + self.ttl_seconds, snapshot)

    def invalidate(self) -> None:
        with self._lock:
            self._items.clear()


inventory_defaults_cache = InventoryDefaultsCache()


class SettingsService:
    def __init__(
        self,
        unit_of_work: SettingsUnitOfWork,
        cache: InventoryDefaultsCache = inventory_defaults_cache,
    ) -> None:
        self.uow = unit_of_work
        self.cache = cache

    def create_category(self, code: str, name: str) -> SettingsCategory:
        item = SettingsCategory(code=code, name=name)
        if self.uow.categories.get_by_code(item.code):
            raise ConflictError("Settings category code already exists")
        self.uow.categories.add(item)
        self.uow.commit()
        return item

    def list_categories(self) -> list[SettingsCategory]:
        return self.uow.categories.list()

    def create_definition(
        self,
        *,
        category_id: UUID,
        key: str,
        name: str,
        value_type: ValueType,
        default_value: Any,
        allowed_scopes: tuple[SettingScope, ...],
        is_required: bool,
        options: tuple[str, ...],
    ) -> SettingDefinition:
        if not self.uow.categories.get(category_id):
            raise NotFoundError("Settings category not found")
        item = SettingDefinition(
            category_id=category_id,
            key=key,
            name=name,
            value_type=value_type,
            default_value=default_value,
            allowed_scopes=allowed_scopes,
            is_required=is_required,
            options=options,
        )
        if self.uow.definitions.get_by_key(item.key):
            raise ConflictError("Setting key already exists")
        self.uow.definitions.add(item)
        self.uow.commit()
        self.cache.invalidate()
        return item

    def get_definition(self, key: str) -> SettingDefinition:
        item = self.uow.definitions.get_by_key(validate_code(key))
        if item is None:
            raise NotFoundError("Setting definition not found")
        return item

    def list_definitions(self, category_id: UUID | None = None) -> list[SettingDefinition]:
        return self.uow.definitions.list(category_id)

    def list_values(self, key: str) -> list[SettingValue]:
        definition = self.get_definition(key)
        return self.uow.values.list(definition.id)

    def set_value(
        self,
        *,
        key: str,
        scope_type: SettingScope,
        scope_id: UUID | None,
        value: Any,
        actor_id: UUID,
        expected_version: int | None = None,
    ) -> SettingValue:
        definition = self.get_definition(key)
        if scope_type not in definition.allowed_scopes:
            raise ValidationError("Scope is not allowed for this setting")
        self._validate_scope_target(scope_type, scope_id)
        validated = canonical_value(value, definition.value_type, definition.options)
        existing = self.uow.values.get(definition.id, scope_type, scope_id)
        if existing is None:
            if expected_version is not None:
                raise ConflictError("Setting version does not match")
            item = SettingValue(
                definition_id=definition.id,
                scope_type=scope_type,
                scope_id=scope_id,
                value=validated,
                updated_by=actor_id,
            )
            self.uow.values.add(item)
        else:
            if expected_version is None or existing.version != expected_version:
                raise ConflictError("Setting version does not match")
            item = SettingValue(
                id=existing.id,
                definition_id=existing.definition_id,
                scope_type=existing.scope_type,
                scope_id=existing.scope_id,
                value=validated,
                version=existing.version + 1,
                updated_at=utc_now(),
                updated_by=actor_id,
            )
            if not self.uow.values.save(item, expected_version):
                raise ConflictError("Setting was changed concurrently")
        self.uow.commit()
        self.cache.invalidate()
        return item

    def resolve(self, key: str, context: SettingsContext) -> ResolvedSetting:
        definition = self.get_definition(key)
        context = self._normalize_context(context)
        for scope_type, scope_id in context.candidates():
            if scope_type not in definition.allowed_scopes:
                continue
            override = self.uow.values.get(definition.id, scope_type, scope_id)
            if override is not None:
                return ResolvedSetting(definition.key, override.value, scope_type, scope_id)
        if definition.default_value is None and definition.is_required:
            raise ValidationError("Required setting has no resolved value")
        return ResolvedSetting(definition.key, definition.default_value, None, None)

    def resolve_inventory_defaults(self, context: SettingsContext) -> InventoryDefaults:
        context = self._normalize_context(context)
        cached = self.cache.get(context)
        if cached is not None:
            return cached
        strategy = self.resolve(SettingsKey.DEFAULT_ISSUE_STRATEGY, context).value
        negative = self.resolve(SettingsKey.NEGATIVE_STOCK_ALLOWED, context).value
        if strategy not in InventoryIssueStrategy or type(negative) is not bool:
            raise ValidationError("Inventory defaults are not valid")
        snapshot = InventoryDefaults(InventoryIssueStrategy(strategy), negative, datetime.now(UTC))
        self.cache.put(context, snapshot)
        return snapshot

    def _validate_scope_target(self, scope_type: SettingScope, scope_id: UUID | None) -> None:
        if scope_type is SettingScope.GLOBAL:
            if scope_id is not None:
                raise ValidationError("GLOBAL setting must not have scope_id")
        elif scope_id is None:
            raise ValidationError("Scoped setting requires scope_id")
        elif scope_type is SettingScope.PRODUCT and not self.uow.scopes.product_category(scope_id):
            raise NotFoundError("Product scope target not found")
        elif scope_type is SettingScope.CATEGORY and not self.uow.scopes.category_exists(scope_id):
            raise NotFoundError("Category scope target not found")
        elif scope_type is SettingScope.WAREHOUSE and not self.uow.scopes.warehouse_exists(
            scope_id
        ):
            raise NotFoundError("Warehouse scope target not found")

    def _normalize_context(self, context: SettingsContext) -> SettingsContext:
        category_id = context.category_id
        if context.product_id is not None:
            actual_category = self.uow.scopes.product_category(context.product_id)
            if actual_category is None:
                raise NotFoundError("Product scope target not found")
            if category_id is not None and category_id != actual_category:
                raise ValidationError("Category does not match product")
            category_id = actual_category
        elif category_id is not None and not self.uow.scopes.category_exists(category_id):
            raise NotFoundError("Category scope target not found")
        if context.warehouse_id is not None and not self.uow.scopes.warehouse_exists(
            context.warehouse_id
        ):
            raise NotFoundError("Warehouse scope target not found")
        return SettingsContext(
            company_id=context.company_id,
            warehouse_id=context.warehouse_id,
            category_id=category_id,
            product_id=context.product_id,
        )
