from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_erp.catalog.domain.entities import (
    Category,
    MeasurementUse,
    Package,
    PackageSet,
    PackageSetKind,
    Product,
    ProductBarcode,
    ProductInventoryPolicy,
    ProductMeasurement,
    Unit,
    UnitDimension,
)
from warehouse_erp.catalog.infrastructure.models import (
    CategoryModel,
    PackageModel,
    PackageSetModel,
    ProductBarcodeModel,
    ProductMeasurementModel,
    ProductModel,
    UnitModel,
)
from warehouse_erp.shared.errors import ConflictError


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _category(model: CategoryModel) -> Category:
    return Category(
        id=UUID(model.id),
        parent_id=UUID(model.parent_id) if model.parent_id else None,
        code=model.code,
        name=model.name,
        description=model.description,
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _unit(model: UnitModel) -> Unit:
    return Unit(
        id=UUID(model.id),
        code=model.code,
        name=model.name,
        symbol=model.symbol,
        dimension=UnitDimension(model.dimension),
        classifier_code=model.classifier_code,
        base_unit_id=UUID(model.base_unit_id) if model.base_unit_id else None,
        factor_to_base=model.factor_to_base,
        display_decimal_places=model.display_decimal_places,
        precision=model.precision,
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _product(model: ProductModel) -> Product:
    return Product(
        id=UUID(model.id),
        code=model.code,
        name=model.name,
        category_id=UUID(model.category_id),
        default_vat_rate_id=UUID(model.default_vat_rate_id) if model.default_vat_rate_id else None,
        storage_unit_id=UUID(model.storage_unit_id),
        package_set_id=UUID(model.package_set_id) if model.package_set_id else None,
        description=model.description,
        brand=model.brand,
        attributes=dict(model.attributes),
        policy=ProductInventoryPolicy(
            batch_expiry_required=model.batch_expiry_required,
        ),
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _with_filters(statement: Select, model: type, *, active: bool | None) -> Select:
    if active is not None:
        statement = statement.where(model.active == active)
    return statement


class SqlAlchemyCategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._tree: dict[UUID, Category] | None = None
        self._locked_models: list[CategoryModel] = []

    def lock_tree(self) -> None:
        # Current locking reads also bypass an earlier REPEATABLE READ snapshot.
        rows = self.session.scalars(
            select(CategoryModel)
            .order_by(CategoryModel.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        self._locked_models = rows
        self._tree = {UUID(row.id): _category(row) for row in rows}

    def clear_tree_cache(self) -> None:
        self._tree = None
        self._locked_models.clear()

    def add(self, category: Category) -> None:
        self.session.add(self._model(category))

    def save(self, category: Category) -> None:
        self.session.merge(self._model(category))

    def get(self, category_id: UUID) -> Category | None:
        if self._tree is not None:
            return self._tree.get(category_id)
        model = self.session.get(CategoryModel, str(category_id))
        return _category(model) if model else None

    def get_by_code(self, code: str) -> Category | None:
        model = self.session.scalar(select(CategoryModel).where(CategoryModel.code == code))
        return _category(model) if model else None

    def list(
        self,
        *,
        limit: int,
        offset: int,
        active: bool | None,
        parent_id: UUID | None,
        root_only: bool,
    ) -> list[Category]:
        statement = select(CategoryModel).order_by(CategoryModel.name, CategoryModel.id)
        statement = _with_filters(statement, CategoryModel, active=active)
        if parent_id is not None:
            statement = statement.where(CategoryModel.parent_id == str(parent_id))
        elif root_only:
            statement = statement.where(CategoryModel.parent_id.is_(None))
        rows = self.session.scalars(statement.offset(offset).limit(limit))
        return [_category(row) for row in rows]

    @staticmethod
    def _model(category: Category) -> CategoryModel:
        return CategoryModel(
            id=str(category.id),
            parent_id=str(category.parent_id) if category.parent_id else None,
            code=category.code,
            name=category.name,
            description=category.description,
            active=category.active,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )


class SqlAlchemyUnitRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, unit: Unit) -> None:
        self.session.add(self._model(unit))

    def save(self, unit: Unit) -> None:
        self.session.merge(self._model(unit))

    def get(self, unit_id: UUID) -> Unit | None:
        model = self.session.get(UnitModel, str(unit_id))
        return _unit(model) if model else None

    def get_by_code(self, code: str) -> Unit | None:
        model = self.session.scalar(select(UnitModel).where(UnitModel.code == code))
        return _unit(model) if model else None

    def list(self, *, limit: int, offset: int, active: bool | None) -> list[Unit]:
        statement = select(UnitModel).order_by(UnitModel.name, UnitModel.id)
        statement = _with_filters(statement, UnitModel, active=active)
        return [_unit(row) for row in self.session.scalars(statement.offset(offset).limit(limit))]

    @staticmethod
    def _model(unit: Unit) -> UnitModel:
        return UnitModel(
            id=str(unit.id),
            code=unit.code,
            name=unit.name,
            symbol=unit.symbol,
            dimension=unit.dimension.value,
            classifier_code=unit.classifier_code,
            base_unit_id=str(unit.base_unit_id) if unit.base_unit_id else None,
            factor_to_base=unit.factor_to_base,
            display_decimal_places=unit.display_decimal_places,
            precision=unit.precision,
            active=unit.active,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
        )


class SqlAlchemyProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.locked_models: dict[str, ProductModel] = {}

    def validate_vat_reference(self, vat_rate_id: UUID) -> None:
        from warehouse_erp.configuration.infrastructure.models import VatRateModel
        from warehouse_erp.configuration.infrastructure.repositories import (
            SqlAlchemyConfigurationRepository,
        )
        from warehouse_erp.shared.errors import ValidationError

        SqlAlchemyConfigurationRepository(self.session).lock()
        found = self.session.scalar(
            select(VatRateModel.id)
            .where(VatRateModel.id == str(vat_rate_id), VatRateModel.active.is_(True))
            .with_for_update()
        )
        if found is None:
            raise ValidationError("VAT rate is missing or inactive")

    def add(self, product: Product) -> None:
        self.session.add(self._model(product))

    def save(self, product: Product) -> None:
        self.session.merge(self._model(product))

    def get(self, product_id: UUID) -> Product | None:
        model = self.session.get(ProductModel, str(product_id))
        return _product(model) if model else None

    def get_by_code(self, code: str) -> Product | None:
        model = self.session.scalar(select(ProductModel).where(ProductModel.code == code))
        return _product(model) if model else None

    def get_for_update(self, product_id: UUID) -> Product | None:
        model = self.session.scalar(
            select(ProductModel)
            .where(ProductModel.id == str(product_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if model is not None:
            # Keep the refreshed ORM row alive until merge/commit; Session uses weak references.
            self.locked_models[model.id] = model
        return _product(model) if model else None

    def get_by_package_set(self, package_set_id: UUID) -> Product | None:
        model = self.session.scalar(
            select(ProductModel)
            .where(ProductModel.package_set_id == str(package_set_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return _product(model) if model else None

    def list_by_package_set(self, package_set_id: UUID) -> list[Product]:
        return [
            _product(row)
            for row in self.session.scalars(
                select(ProductModel).where(ProductModel.package_set_id == str(package_set_id))
            )
        ]

    def list(
        self, *, limit: int, offset: int, active: bool | None, category_id: UUID | None
    ) -> list[Product]:
        statement = select(ProductModel).order_by(ProductModel.name, ProductModel.id)
        statement = _with_filters(statement, ProductModel, active=active)
        if category_id is not None:
            statement = statement.where(ProductModel.category_id == str(category_id))
        rows = self.session.scalars(statement.offset(offset).limit(limit))
        return [_product(row) for row in rows]

    @staticmethod
    def _model(product: Product) -> ProductModel:
        return ProductModel(
            id=str(product.id),
            code=product.code,
            name=product.name,
            category_id=str(product.category_id),
            default_vat_rate_id=str(product.default_vat_rate_id)
            if product.default_vat_rate_id
            else None,
            storage_unit_id=str(product.storage_unit_id),
            package_set_id=str(product.package_set_id) if product.package_set_id else None,
            description=product.description,
            brand=product.brand,
            attributes=product.attributes,
            batch_expiry_required=product.policy.batch_expiry_required,
            active=product.active,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


def _package_set(model: PackageSetModel) -> PackageSet:
    return PackageSet(
        id=UUID(model.id),
        code=model.code,
        name=model.name,
        kind=PackageSetKind(model.kind),
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _package(model: PackageModel) -> Package:
    return Package(
        id=UUID(model.id),
        package_set_id=UUID(model.package_set_id),
        code=model.code,
        name=model.name,
        unit_id=UUID(model.unit_id),
        contains_quantity=model.contains_quantity,
        contains_package_id=UUID(model.contains_package_id) if model.contains_package_id else None,
        contains_unit_id=UUID(model.contains_unit_id) if model.contains_unit_id else None,
        weight=model.weight,
        weight_unit_id=UUID(model.weight_unit_id) if model.weight_unit_id else None,
        volume=model.volume,
        volume_unit_id=UUID(model.volume_unit_id) if model.volume_unit_id else None,
        length=model.length,
        width=model.width,
        height=model.height,
        dimension_unit_id=UUID(model.dimension_unit_id) if model.dimension_unit_id else None,
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _measurement(model: ProductMeasurementModel) -> ProductMeasurement:
    return ProductMeasurement(
        id=UUID(model.id),
        product_id=UUID(model.product_id),
        unit_id=UUID(model.unit_id),
        storage_quantity=model.storage_quantity,
        measured_quantity=model.measured_quantity,
        use=MeasurementUse(model.use),
        is_report_unit=model.is_report_unit,
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


def _barcode(model: ProductBarcodeModel) -> ProductBarcode:
    return ProductBarcode(
        id=UUID(model.id),
        product_id=UUID(model.product_id),
        value=model.value,
        package_id=UUID(model.package_id) if model.package_id else None,
        active=model.active,
        created_at=_utc(model.created_at),
        updated_at=_utc(model.updated_at),
    )


class SqlAlchemyPackageSetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: PackageSet) -> None:
        self.session.add(self._model(item))

    def save(self, item: PackageSet) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> PackageSet | None:
        model = self.session.get(PackageSetModel, str(item_id))
        return _package_set(model) if model else None

    def get_by_code(self, code: str) -> PackageSet | None:
        model = self.session.scalar(select(PackageSetModel).where(PackageSetModel.code == code))
        return _package_set(model) if model else None

    def lock(self, item_id: UUID) -> None:
        self.session.execute(
            select(PackageSetModel.id).where(PackageSetModel.id == str(item_id)).with_for_update()
        ).one()

    def list(self, *, limit: int, offset: int, active: bool | None) -> list[PackageSet]:
        statement = _with_filters(
            select(PackageSetModel).order_by(PackageSetModel.name, PackageSetModel.id),
            PackageSetModel,
            active=active,
        )
        return [
            _package_set(row) for row in self.session.scalars(statement.offset(offset).limit(limit))
        ]

    @staticmethod
    def _model(item: PackageSet) -> PackageSetModel:
        return PackageSetModel(
            id=str(item.id),
            code=item.code,
            name=item.name,
            kind=item.kind.value,
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SqlAlchemyPackageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: Package) -> None:
        self.session.add(self._model(item))

    def save(self, item: Package) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> Package | None:
        model = self.session.get(PackageModel, str(item_id))
        return _package(model) if model else None

    def get_by_code(self, package_set_id: UUID, code: str) -> Package | None:
        model = self.session.scalar(
            select(PackageModel).where(
                PackageModel.package_set_id == str(package_set_id),
                PackageModel.code == code,
            )
        )
        return _package(model) if model else None

    def list(self, package_set_id: UUID, *, active: bool | None) -> list[Package]:
        statement = _with_filters(
            select(PackageModel)
            .where(PackageModel.package_set_id == str(package_set_id))
            .order_by(PackageModel.name, PackageModel.id),
            PackageModel,
            active=active,
        )
        return [_package(row) for row in self.session.scalars(statement)]

    @staticmethod
    def _model(item: Package) -> PackageModel:
        return PackageModel(
            id=str(item.id),
            package_set_id=str(item.package_set_id),
            code=item.code,
            name=item.name,
            unit_id=str(item.unit_id),
            contains_package_id=str(item.contains_package_id) if item.contains_package_id else None,
            contains_unit_id=str(item.contains_unit_id) if item.contains_unit_id else None,
            contains_quantity=item.contains_quantity,
            weight=item.weight,
            weight_unit_id=str(item.weight_unit_id) if item.weight_unit_id else None,
            volume=item.volume,
            volume_unit_id=str(item.volume_unit_id) if item.volume_unit_id else None,
            length=item.length,
            width=item.width,
            height=item.height,
            dimension_unit_id=str(item.dimension_unit_id) if item.dimension_unit_id else None,
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SqlAlchemyMeasurementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: ProductMeasurement) -> None:
        self.session.add(self._model(item))

    def save(self, item: ProductMeasurement) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> ProductMeasurement | None:
        model = self.session.get(ProductMeasurementModel, str(item_id))
        return _measurement(model) if model else None

    def get_by_unit(self, product_id: UUID, unit_id: UUID) -> ProductMeasurement | None:
        model = self.session.scalar(
            select(ProductMeasurementModel).where(
                ProductMeasurementModel.product_id == str(product_id),
                ProductMeasurementModel.unit_id == str(unit_id),
            )
        )
        return _measurement(model) if model else None

    def list(self, product_id: UUID, *, active: bool | None) -> list[ProductMeasurement]:
        statement = _with_filters(
            select(ProductMeasurementModel)
            .where(ProductMeasurementModel.product_id == str(product_id))
            .order_by(ProductMeasurementModel.id),
            ProductMeasurementModel,
            active=active,
        )
        return [_measurement(row) for row in self.session.scalars(statement)]

    @staticmethod
    def _model(item: ProductMeasurement) -> ProductMeasurementModel:
        return ProductMeasurementModel(
            id=str(item.id),
            product_id=str(item.product_id),
            unit_id=str(item.unit_id),
            storage_quantity=item.storage_quantity,
            measured_quantity=item.measured_quantity,
            use=item.use.value,
            is_report_unit=item.is_report_unit,
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SqlAlchemyBarcodeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.locked_models: dict[str, ProductBarcodeModel] = {}

    def add(self, item: ProductBarcode) -> None:
        self.session.add(self._model(item))

    def save(self, item: ProductBarcode) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> ProductBarcode | None:
        model = self.session.get(ProductBarcodeModel, str(item_id))
        return _barcode(model) if model else None

    def get_for_update(self, item_id: UUID) -> ProductBarcode | None:
        model = self.session.scalar(
            select(ProductBarcodeModel)
            .where(ProductBarcodeModel.id == str(item_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if model is not None:
            self.locked_models[model.id] = model
        return _barcode(model) if model else None

    def get_by_value(self, value: str) -> ProductBarcode | None:
        model = self.session.scalar(
            select(ProductBarcodeModel).where(ProductBarcodeModel.value == value)
        )
        return _barcode(model) if model else None

    def list(
        self, product_id: UUID, *, active: bool | None, for_update: bool = False
    ) -> list[ProductBarcode]:
        statement = _with_filters(
            select(ProductBarcodeModel)
            .where(ProductBarcodeModel.product_id == str(product_id))
            .order_by(ProductBarcodeModel.id),
            ProductBarcodeModel,
            active=active,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return [_barcode(row) for row in self.session.scalars(statement)]

    @staticmethod
    def _model(item: ProductBarcode) -> ProductBarcodeModel:
        return ProductBarcodeModel(
            id=str(item.id),
            product_id=str(item.product_id),
            value=item.value,
            package_id=str(item.package_id) if item.package_id else None,
            active=item.active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SqlAlchemyCatalogUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.categories = SqlAlchemyCategoryRepository(session)
        self.units = SqlAlchemyUnitRepository(session)
        self.products = SqlAlchemyProductRepository(session)
        self.package_sets = SqlAlchemyPackageSetRepository(session)
        self.packages = SqlAlchemyPackageRepository(session)
        self.measurements = SqlAlchemyMeasurementRepository(session)
        self.barcodes = SqlAlchemyBarcodeRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Catalog data conflicts with an existing record") from exc
        finally:
            self.categories.clear_tree_cache()
            self.products.locked_models.clear()
            self.barcodes.locked_models.clear()

    def rollback(self) -> None:
        self.session.rollback()
        self.categories.clear_tree_cache()
        self.products.locked_models.clear()
        self.barcodes.locked_models.clear()
