from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_erp.catalog.infrastructure.models import CategoryModel, ProductModel
from warehouse_erp.inventory.domain.policies import (
    IssueStrategy,
    TrackingMode,
    WarehouseInventoryPolicy,
)
from warehouse_erp.settings.domain.entities import (
    SettingDefinition,
    SettingsCategory,
    SettingScope,
    SettingValue,
    ValueType,
)
from warehouse_erp.settings.infrastructure.models import (
    SettingDefinitionModel,
    SettingsCategoryModel,
    SettingValueModel,
)
from warehouse_erp.shared.errors import ConflictError, NotFoundError
from warehouse_erp.warehouse.infrastructure.models import WarehouseModel


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _category(model: SettingsCategoryModel) -> SettingsCategory:
    return SettingsCategory(
        id=UUID(model.id), code=model.code, name=model.name, created_at=_utc(model.created_at)
    )


def _definition(model: SettingDefinitionModel) -> SettingDefinition:
    return SettingDefinition(
        id=UUID(model.id),
        category_id=UUID(model.category_id),
        key=model.key,
        name=model.name,
        value_type=ValueType(model.value_type),
        default_value=model.default_value,
        allowed_scopes=tuple(SettingScope(value) for value in model.allowed_scopes),
        is_required=model.is_required,
        options=tuple(model.options),
        created_at=_utc(model.created_at),
    )


def _value(model: SettingValueModel) -> SettingValue:
    return SettingValue(
        id=UUID(model.id),
        definition_id=UUID(model.definition_id),
        scope_type=SettingScope(model.scope_type),
        scope_id=UUID(model.scope_id) if model.scope_id else None,
        value=model.value,
        version=model.version,
        updated_at=_utc(model.updated_at),
        updated_by=UUID(model.updated_by),
    )


class SqlAlchemySettingsCategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: SettingsCategory) -> None:
        self.session.add(
            SettingsCategoryModel(
                id=str(item.id), code=item.code, name=item.name, created_at=item.created_at
            )
        )

    def get(self, item_id: UUID) -> SettingsCategory | None:
        model = self.session.get(SettingsCategoryModel, str(item_id))
        return _category(model) if model else None

    def get_by_code(self, code: str) -> SettingsCategory | None:
        model = self.session.scalar(
            select(SettingsCategoryModel).where(SettingsCategoryModel.code == code)
        )
        return _category(model) if model else None

    def list(self) -> list[SettingsCategory]:
        return [
            _category(row)
            for row in self.session.scalars(
                select(SettingsCategoryModel).order_by(SettingsCategoryModel.code)
            )
        ]


class SqlAlchemySettingDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: SettingDefinition) -> None:
        self.session.add(
            SettingDefinitionModel(
                id=str(item.id),
                category_id=str(item.category_id),
                key=item.key,
                name=item.name,
                value_type=item.value_type.value,
                default_value=item.default_value,
                allowed_scopes=[scope.value for scope in item.allowed_scopes],
                is_required=item.is_required,
                options=list(item.options),
                created_at=item.created_at,
            )
        )

    def get(self, item_id: UUID) -> SettingDefinition | None:
        model = self.session.get(SettingDefinitionModel, str(item_id))
        return _definition(model) if model else None

    def get_by_key(self, key: str) -> SettingDefinition | None:
        model = self.session.scalar(
            select(SettingDefinitionModel).where(SettingDefinitionModel.key == key)
        )
        return _definition(model) if model else None

    def list(self, category_id: UUID | None) -> list[SettingDefinition]:
        statement = select(SettingDefinitionModel).order_by(SettingDefinitionModel.key)
        if category_id is not None:
            statement = statement.where(SettingDefinitionModel.category_id == str(category_id))
        return [_definition(row) for row in self.session.scalars(statement)]


class SqlAlchemySettingValueRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: SettingValue) -> None:
        self.session.add(
            SettingValueModel(
                id=str(item.id),
                definition_id=str(item.definition_id),
                scope_type=item.scope_type.value,
                scope_id=str(item.scope_id) if item.scope_id else None,
                scope_key=item.scope_key,
                value=item.value,
                version=item.version,
                updated_at=item.updated_at,
                updated_by=str(item.updated_by),
            )
        )

    def save(self, item: SettingValue, expected_version: int) -> bool:
        result = self.session.execute(
            update(SettingValueModel)
            .where(
                SettingValueModel.id == str(item.id),
                SettingValueModel.version == expected_version,
            )
            .values(
                value=item.value,
                version=item.version,
                updated_at=item.updated_at,
                updated_by=str(item.updated_by),
            )
        )
        return result.rowcount == 1

    def get(
        self, definition_id: UUID, scope_type: SettingScope, scope_id: UUID | None
    ) -> SettingValue | None:
        scope_key = "GLOBAL" if scope_id is None else str(scope_id)
        model = self.session.scalar(
            select(SettingValueModel).where(
                SettingValueModel.definition_id == str(definition_id),
                SettingValueModel.scope_type == scope_type.value,
                SettingValueModel.scope_key == scope_key,
            )
        )
        return _value(model) if model else None

    def list(self, definition_id: UUID) -> list[SettingValue]:
        return [
            _value(row)
            for row in self.session.scalars(
                select(SettingValueModel)
                .where(SettingValueModel.definition_id == str(definition_id))
                .order_by(SettingValueModel.scope_type, SettingValueModel.scope_key)
            )
        ]


class SqlAlchemySettingsUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.categories = SqlAlchemySettingsCategoryRepository(session)
        self.definitions = SqlAlchemySettingDefinitionRepository(session)
        self.values = SqlAlchemySettingValueRepository(session)
        self.scopes = SqlAlchemySettingScopeRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Settings conflict with an existing record") from exc

    def rollback(self) -> None:
        self.session.rollback()


class SqlAlchemySettingScopeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def cost_accounting_enabled(self, *, lock: bool = False) -> bool:
        from warehouse_erp.configuration.application.service import settings_id
        from warehouse_erp.configuration.infrastructure.models import AccountingSettingsModel
        from warehouse_erp.configuration.infrastructure.repositories import (
            SqlAlchemyConfigurationRepository,
        )

        if lock:
            SqlAlchemyConfigurationRepository(self.session).lock()
        query = select(AccountingSettingsModel.cost_accounting_enabled).where(
            AccountingSettingsModel.id == str(settings_id("accounting"))
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query) is True

    def product_category(self, product_id: UUID) -> UUID | None:
        model = self.session.get(ProductModel, str(product_id))
        return UUID(model.category_id) if model else None

    def category_exists(self, category_id: UUID) -> bool:
        return self.session.get(CategoryModel, str(category_id)) is not None

    def warehouse_exists(self, warehouse_id: UUID) -> bool:
        return self.session.get(WarehouseModel, str(warehouse_id)) is not None

    def warehouse_inventory_policy(self, warehouse_id: UUID) -> WarehouseInventoryPolicy:
        model = self.session.get(WarehouseModel, str(warehouse_id))
        if model is None:
            raise NotFoundError("Warehouse scope target not found")
        return WarehouseInventoryPolicy(
            TrackingMode(model.tracking_mode), IssueStrategy(model.issue_strategy)
        )

    def product_expiry_required(self, product_id: UUID) -> bool:
        model = self.session.get(ProductModel, str(product_id))
        if model is None:
            raise NotFoundError("Product scope target not found")
        return model.batch_expiry_required
