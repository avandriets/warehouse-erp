from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from warehouse_erp.catalog.application.commands import (
    CreateCategory,
    CreatePackage,
    CreatePackageSet,
    CreateProduct,
    CreateProductBarcode,
    CreateProductMeasurement,
    CreateUnit,
    InventoryPolicyData,
    UpdateCategory,
    UpdatePackage,
    UpdatePackageSet,
    UpdateProduct,
    UpdateProductBarcode,
    UpdateProductMeasurement,
    UpdateUnit,
)
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
    normalize_code,
    utc_now,
    validate_name,
)
from warehouse_erp.catalog.domain.quantities import (
    exact_decimal,
    storage_quantity,
    validate_quantity,
)
from warehouse_erp.catalog.domain.repositories import CatalogUnitOfWork
from warehouse_erp.shared.errors import ConflictError, NotFoundError, ValidationError


class CatalogService:
    def __init__(self, unit_of_work: CatalogUnitOfWork) -> None:
        self.uow = unit_of_work

    def create_category(self, command: CreateCategory) -> Category:
        code = normalize_code(command.code)
        if self.uow.categories.get_by_code(code):
            raise ConflictError(f"Category with code {code} already exists")
        if command.parent_id is not None:
            self._require_active_category(command.parent_id)
        category = Category(
            code=code,
            name=command.name,
            parent_id=command.parent_id,
            description=command.description,
        )
        self.uow.categories.add(category)
        self.uow.commit()
        return category

    def get_category(self, category_id: UUID) -> Category:
        category = self.uow.categories.get(category_id)
        if not category:
            raise NotFoundError("Category not found")
        return category

    def list_categories(
        self,
        *,
        limit: int,
        offset: int,
        active: bool | None,
        parent_id: UUID | None,
        root_only: bool,
    ) -> list[Category]:
        return self.uow.categories.list(
            limit=limit,
            offset=offset,
            active=active,
            parent_id=parent_id,
            root_only=root_only,
        )

    def update_category(self, category_id: UUID, command: UpdateCategory) -> Category:
        self.uow.categories.lock_tree()
        category = self.get_category(category_id)
        if command.name is not None:
            category.name = validate_name(command.name)
        if command.parent_id_set:
            if command.parent_id is not None:
                self._validate_category_parent(category.id, command.parent_id)
            category.parent_id = command.parent_id
        if command.description is not None:
            category.description = command.description
        if command.active is not None:
            category.active = command.active
        category.updated_at = utc_now()
        self.uow.categories.save(category)
        self.uow.commit()
        return category

    def create_unit(self, command: CreateUnit) -> Unit:
        code = normalize_code(command.code)
        if self.uow.units.get_by_code(code):
            raise ConflictError(f"Unit with code {code} already exists")
        if command.base_unit_id is not None:
            base_unit = self._require_active_unit(command.base_unit_id)
            if base_unit.base_unit_id is not None or base_unit.dimension is not command.dimension:
                raise ValidationError("Base unit must be a root unit of the same dimension")
        unit = Unit(
            code=code,
            name=command.name,
            symbol=command.symbol,
            dimension=command.dimension,
            display_decimal_places=command.display_decimal_places,
            precision=command.precision,
            classifier_code=command.classifier_code,
            base_unit_id=command.base_unit_id,
            factor_to_base=command.factor_to_base,
        )
        self.uow.units.add(unit)
        self.uow.commit()
        return unit

    def get_unit(self, unit_id: UUID) -> Unit:
        unit = self.uow.units.get(unit_id)
        if not unit:
            raise NotFoundError("Unit not found")
        return unit

    def list_units(self, *, limit: int, offset: int, active: bool | None) -> list[Unit]:
        return self.uow.units.list(limit=limit, offset=offset, active=active)

    def update_unit(self, unit_id: UUID, command: UpdateUnit) -> Unit:
        unit = self.get_unit(unit_id)
        if command.name is not None:
            unit.name = validate_name(command.name)
        if command.symbol is not None:
            symbol = command.symbol.strip()
            if not symbol or len(symbol) > 32:
                raise ValidationError("unit symbol must be between 1 and 32 characters")
            unit.symbol = symbol
        if command.dimension is not None and command.dimension != unit.dimension:
            if unit.dimension is not UnitDimension.OTHER:
                raise ValidationError("Established unit dimension cannot be changed")
            unit.dimension = command.dimension
        if command.classifier_code_set:
            unit.classifier_code = (
                command.classifier_code.strip() or None if command.classifier_code else None
            )
        if command.display_decimal_places is not None:
            if not 0 <= command.display_decimal_places <= 9:
                raise ValidationError("display_decimal_places must be between 0 and 9")
            unit.display_decimal_places = command.display_decimal_places
        if command.precision is not None:
            if not 0 <= command.precision <= 6:
                raise ValidationError("precision must be between 0 and 6")
            unit.precision = command.precision
        if command.active is not None:
            unit.active = command.active
        unit.updated_at = utc_now()
        self.uow.units.save(unit)
        self.uow.commit()
        return unit

    def convert_unit_quantity(
        self, *, quantity: Decimal, from_unit_id: UUID, to_unit_id: UUID
    ) -> Decimal:
        validate_quantity(quantity)
        source = self._require_active_unit(from_unit_id)
        target = self._require_active_unit(to_unit_id)
        if source.id == target.id:
            return storage_quantity(Fraction(quantity), target.precision)
        if source.dimension != target.dimension:
            raise ValidationError("Cannot convert between different unit dimensions")
        source_base = source.base_unit_id or source.id
        target_base = target.base_unit_id or target.id
        if source_base != target_base or not source.factor_to_base and not target.factor_to_base:
            raise ValidationError("Units do not share a conversion base")
        result = (
            Fraction(quantity)
            * Fraction(source.factor_to_base or 1)
            / Fraction(target.factor_to_base or 1)
        )
        return storage_quantity(result, target.precision)

    def create_package_set(self, command: CreatePackageSet) -> PackageSet:
        code = normalize_code(command.code)
        if self.uow.package_sets.get_by_code(code):
            raise ConflictError("Package set code already exists")
        item = PackageSet(code=code, name=command.name, kind=command.kind)
        self.uow.package_sets.add(item)
        self.uow.commit()
        return item

    def get_package_set(self, item_id: UUID) -> PackageSet:
        item = self.uow.package_sets.get(item_id)
        if item is None:
            raise NotFoundError("Package set not found")
        return item

    def list_package_sets(
        self, *, limit: int, offset: int, active: bool | None
    ) -> list[PackageSet]:
        return self.uow.package_sets.list(limit=limit, offset=offset, active=active)

    def update_package_set(self, item_id: UUID, command: UpdatePackageSet) -> PackageSet:
        item = self.get_package_set(item_id)
        if command.name is not None:
            item.name = validate_name(command.name)
        if command.active is not None:
            item.active = command.active
        item.updated_at = utc_now()
        self.uow.package_sets.save(item)
        self.uow.commit()
        return item

    def get_package(self, item_id: UUID) -> Package:
        item = self.uow.packages.get(item_id)
        if item is None:
            raise NotFoundError("Package not found")
        return item

    def list_packages(self, package_set_id: UUID, *, active: bool | None) -> list[Package]:
        self.get_package_set(package_set_id)
        return self.uow.packages.list(package_set_id, active=active)

    def create_package(self, command: CreatePackage) -> Package:
        package_set = self.get_package_set(command.package_set_id)
        if not package_set.active:
            raise ValidationError("Package set is inactive")
        code = normalize_code(command.code)
        if self.uow.packages.get_by_code(package_set.id, code):
            raise ConflictError("Package code already exists in this set")
        package_unit = self._require_unit_dimension(command.unit_id, UnitDimension.COUNT)
        if package_unit.precision != 0:
            raise ValidationError("Packaging unit must have zero decimal precision")
        if command.weight_unit_id:
            self._require_unit_dimension(command.weight_unit_id, UnitDimension.MASS)
        if command.volume_unit_id:
            self._require_unit_dimension(command.volume_unit_id, UnitDimension.VOLUME)
        if command.dimension_unit_id:
            self._require_unit_dimension(command.dimension_unit_id, UnitDimension.LENGTH)
        if command.contains_package_id:
            child = self.get_package(command.contains_package_id)
            if child.package_set_id != package_set.id or not child.active:
                raise ValidationError("Contained package must be active and in the same set")
        if command.contains_unit_id:
            self._require_active_unit(command.contains_unit_id)
        item = Package(**asdict(command))
        self._validate_package_quantity(item)
        self._validate_linked_package_unit(package_set.id, item)
        self.uow.packages.add(item)
        self.uow.commit()
        return item

    def update_package(self, item_id: UUID, command: UpdatePackage) -> Package:
        item = self.get_package(item_id)
        if command.name is not None:
            item.name = validate_name(command.name)
        if command.contains_quantity is not None:
            if command.contains_quantity <= 0:
                raise ValidationError("contains_quantity must be greater than zero")
            item.contains_quantity = command.contains_quantity
        if command.contains_package_id_set:
            if command.contains_package_id is not None:
                child = self.get_package(command.contains_package_id)
                if child.package_set_id != item.package_set_id or not child.active:
                    raise ValidationError("Contained package must be active and in the same set")
                self._package_factor(child.id, ancestor_id=item.id)
            item.contains_package_id = command.contains_package_id
            if command.contains_package_id:
                item.contains_unit_id = None
        if command.contains_unit_id_set:
            if command.contains_unit_id:
                self._require_active_unit(command.contains_unit_id)
                item.contains_package_id = None
            item.contains_unit_id = command.contains_unit_id
        Package(**asdict(item))
        self._validate_package_quantity(item)
        self._validate_linked_package_unit(item.package_set_id, item)
        if command.active is not None:
            item.active = command.active
        item.updated_at = utc_now()
        self.uow.packages.save(item)
        self.uow.commit()
        return item

    def package_factor(self, product_id: UUID, package_id: UUID) -> Decimal:
        return self._active_package_factor(self.get_product(product_id), package_id)

    def _active_package_factor(self, product: Product, package_id: UUID) -> Decimal:
        package = self.get_package(package_id)
        package_set = self.get_package_set(package.package_set_id)
        if (
            not product.active
            or not package.active
            or not package_set.active
            or product.package_set_id != package.package_set_id
        ):
            raise ValidationError("Package is not active in the product's package set")
        return self._package_factor(package_id, storage_unit_id=product.storage_unit_id)

    def _package_factor(
        self,
        package_id: UUID,
        *,
        storage_unit_id: UUID | None = None,
        ancestor_id: UUID | None = None,
    ) -> Decimal:
        visited: set[UUID] = set()
        factor = Fraction(1)
        current = self.get_package(package_id)
        while True:
            if current.id in visited or current.id == ancestor_id:
                raise ValidationError("Package hierarchy cannot contain a cycle")
            if not current.active:
                raise ValidationError("Package hierarchy contains an inactive package")
            visited.add(current.id)
            factor *= Fraction(current.contains_quantity)
            if current.contains_package_id is None:
                if storage_unit_id is not None and current.contains_unit_id != storage_unit_id:
                    raise ValidationError("Package does not resolve to product storage unit")
                return exact_decimal(factor)
            current = self.get_package(current.contains_package_id)

    def create_product(self, command: CreateProduct) -> Product:
        code = normalize_code(command.code, "product code")
        if self.uow.products.get_by_code(code):
            raise ConflictError(f"Product with code {code} already exists")
        self._require_active_category(command.category_id)
        if command.default_vat_rate_id is not None:
            self.uow.products.validate_vat_reference(command.default_vat_rate_id)
        self._require_active_unit(command.storage_unit_id)
        if command.package_set_id:
            self._validate_package_set(command.package_set_id, command.storage_unit_id)
        product = Product(
            code=code,
            name=command.name,
            category_id=command.category_id,
            default_vat_rate_id=command.default_vat_rate_id,
            storage_unit_id=command.storage_unit_id,
            package_set_id=command.package_set_id,
            description=command.description,
            brand=command.brand,
            attributes=command.attributes,
            policy=self._policy(command.policy),
        )
        self.uow.products.add(product)
        self.uow.commit()
        return product

    def get_product(self, product_id: UUID) -> Product:
        product = self.uow.products.get(product_id)
        if not product:
            raise NotFoundError("Product not found")
        return product

    def list_products(
        self,
        *,
        limit: int,
        offset: int,
        active: bool | None,
        category_id: UUID | None,
    ) -> list[Product]:
        return self.uow.products.list(
            limit=limit, offset=offset, active=active, category_id=category_id
        )

    def update_product(self, product_id: UUID, command: UpdateProduct) -> Product:
        if command.default_vat_rate_id_set and command.default_vat_rate_id is not None:
            self.uow.products.validate_vat_reference(command.default_vat_rate_id)
        product = self._lock_product(product_id)
        if command.name is not None:
            product.name = validate_name(command.name)
        if command.category_id is not None:
            self._require_active_category(command.category_id)
            product.category_id = command.category_id
        if (
            command.storage_unit_id is not None
            and command.storage_unit_id != product.storage_unit_id
        ):
            raise ValidationError(
                "Storage unit is immutable; create a new product for another unit"
            )
        if command.package_set_id_set:
            if command.package_set_id != product.package_set_id:
                if any(
                    barcode.package_id is not None
                    for barcode in self.uow.barcodes.list(product.id, active=True, for_update=True)
                ):
                    raise ConflictError("Deactivate package barcodes before changing package set")
            if command.package_set_id:
                self._validate_package_set(
                    command.package_set_id, product.storage_unit_id, exclude_product_id=product.id
                )
            product.package_set_id = command.package_set_id
        if command.description is not None:
            product.description = command.description
        if command.brand is not None:
            product.brand = command.brand.strip() or None
        if command.attributes is not None:
            product.attributes = command.attributes
        if command.default_vat_rate_id_set:
            product.default_vat_rate_id = command.default_vat_rate_id
        if command.policy is not None:
            product.policy = self._policy(command.policy)
        if command.active is not None:
            product.active = command.active
        product.updated_at = utc_now()
        self.uow.products.save(product)
        self.uow.commit()
        return product

    def _validate_package_set(
        self,
        package_set_id: UUID,
        storage_unit_id: UUID,
        *,
        exclude_product_id: UUID | None = None,
    ) -> None:
        package_set = self.get_package_set(package_set_id)
        if not package_set.active:
            raise ValidationError("Package set is inactive")
        if package_set.kind is PackageSetKind.INDIVIDUAL:
            self.uow.package_sets.lock(package_set_id)
            linked = self.uow.products.get_by_package_set(package_set_id)
            if linked and linked.id != exclude_product_id:
                raise ConflictError("Individual package set already belongs to another product")
        for package in self.uow.packages.list(package_set_id, active=True):
            root = package
            visited: set[UUID] = set()
            while root.contains_package_id is not None:
                if root.id in visited:
                    raise ValidationError("Package hierarchy cannot contain a cycle")
                visited.add(root.id)
                root = self.get_package(root.contains_package_id)
            if root.contains_unit_id != storage_unit_id:
                raise ValidationError("Package set does not match product storage unit")

    def _validate_linked_package_unit(self, package_set_id: UUID, item: Package) -> None:
        for product in self.uow.products.list_by_package_set(package_set_id):
            root = item
            while root.contains_package_id:
                root = self.get_package(root.contains_package_id)
            if root.contains_unit_id != product.storage_unit_id:
                raise ValidationError("Package unit does not match linked product storage unit")

    def _validate_package_quantity(self, item: Package) -> None:
        unit_id = (
            self.get_package(item.contains_package_id).unit_id
            if item.contains_package_id
            else item.contains_unit_id
        )
        if unit_id is None:
            raise ValidationError("Package must contain a unit or another package")
        precision = self.get_unit(unit_id).precision
        if item.contains_quantity != item.contains_quantity.quantize(Decimal(1).scaleb(-precision)):
            raise ValidationError("Package content exceeds contained unit precision")

    def create_measurement(self, command: CreateProductMeasurement) -> ProductMeasurement:
        product = self.get_product(command.product_id)
        unit = self._require_active_unit(command.unit_id)
        if not product.active or unit.id == product.storage_unit_id:
            raise ValidationError("Measurement requires an active product and alternative unit")
        if unit.dimension is UnitDimension.OTHER:
            raise ValidationError("Measurement unit must have a physical dimension")
        if self.uow.measurements.get_by_unit(product.id, unit.id):
            raise ConflictError("Product measurement for this unit already exists")
        item = ProductMeasurement(**asdict(command))
        self._validate_measurement(item)
        self.uow.measurements.add(item)
        self.uow.commit()
        return item

    def list_measurements(
        self, product_id: UUID, *, active: bool | None
    ) -> list[ProductMeasurement]:
        self.get_product(product_id)
        return self.uow.measurements.list(product_id, active=active)

    def update_measurement(
        self, product_id: UUID, item_id: UUID, command: UpdateProductMeasurement
    ) -> ProductMeasurement:
        item = self.uow.measurements.get(item_id)
        if item is None or item.product_id != product_id:
            raise NotFoundError("Product measurement not found")
        for name in ("storage_quantity", "measured_quantity", "use", "is_report_unit", "active"):
            value = getattr(command, name)
            if value is not None:
                setattr(item, name, value)
        self._validate_measurement(item)
        item.updated_at = utc_now()
        self.uow.measurements.save(item)
        self.uow.commit()
        return item

    def _validate_measurement(self, item: ProductMeasurement) -> None:
        if item.storage_quantity <= 0 or item.measured_quantity <= 0:
            raise ValidationError("Measurement quantities must be greater than zero")
        if item.is_report_unit and item.active:
            for existing in self.uow.measurements.list(item.product_id, active=True):
                if existing.id != item.id and existing.is_report_unit:
                    raise ConflictError("Product already has a report unit")

    def create_barcode(self, command: CreateProductBarcode) -> ProductBarcode:
        product = self._lock_product(command.product_id)
        if not product.active:
            raise ValidationError("Product is inactive")
        item = ProductBarcode(**asdict(command))
        if self.uow.barcodes.get_by_value(item.value):
            raise ConflictError("Barcode already exists")
        if command.package_id:
            self._active_package_factor(product, command.package_id)
        self.uow.barcodes.add(item)
        self.uow.commit()
        return item

    def list_barcodes(self, product_id: UUID, *, active: bool | None) -> list[ProductBarcode]:
        self.get_product(product_id)
        return self.uow.barcodes.list(product_id, active=active)

    def update_barcode(
        self, product_id: UUID, item_id: UUID, command: UpdateProductBarcode
    ) -> ProductBarcode:
        product = self._lock_product(product_id)
        item = self.uow.barcodes.get_for_update(item_id)
        if item is None or item.product_id != product_id:
            raise NotFoundError("Product barcode not found")
        if command.active:
            if not product.active:
                raise ValidationError("Product is inactive")
            if item.package_id is not None:
                self._active_package_factor(product, item.package_id)
        item.active = command.active
        item.updated_at = utc_now()
        self.uow.barcodes.save(item)
        self.uow.commit()
        return item

    def _lock_product(self, product_id: UUID) -> Product:
        product = self.uow.products.get_for_update(product_id)
        if product is None:
            raise NotFoundError("Product not found")
        return product

    def convert_to_storage(
        self,
        product_id: UUID,
        *,
        quantity: Decimal,
        package_id: UUID | None = None,
        measurement_id: UUID | None = None,
    ) -> Decimal:
        validate_quantity(quantity)
        if package_id is not None and measurement_id is not None:
            raise ValidationError("Specify positive quantity and at most one conversion")
        product = self.get_product(product_id)
        if package_id:
            result = Fraction(quantity) * Fraction(self.package_factor(product.id, package_id))
        elif measurement_id:
            item = self.uow.measurements.get(measurement_id)
            if (
                item is None
                or item.product_id != product.id
                or not item.active
                or item.use is not MeasurementUse.DOCUMENT
            ):
                raise ValidationError("Measurement is not available in documents")
            result = (
                Fraction(quantity)
                * Fraction(item.storage_quantity)
                / Fraction(item.measured_quantity)
            )
        else:
            result = Fraction(quantity)
        precision = self.get_unit(product.storage_unit_id).precision
        return storage_quantity(result, precision)

    def _require_active_category(self, category_id: UUID) -> Category:
        category = self.get_category(category_id)
        if not category.active:
            raise ValidationError("Category is inactive")
        return category

    def _validate_category_parent(self, category_id: UUID, parent_id: UUID) -> None:
        current = self._require_active_category(parent_id)
        visited: set[UUID] = set()
        while True:
            if current.id == category_id:
                raise ValidationError("Category hierarchy cannot contain a cycle")
            if current.id in visited:
                raise ValidationError("Category hierarchy already contains a cycle")
            visited.add(current.id)
            if current.parent_id is None:
                return
            current = self.get_category(current.parent_id)

    def _require_active_unit(self, unit_id: UUID) -> Unit:
        unit = self.get_unit(unit_id)
        if not unit.active:
            raise ValidationError("Unit is inactive")
        return unit

    def _require_unit_dimension(self, unit_id: UUID, dimension: UnitDimension) -> Unit:
        unit = self._require_active_unit(unit_id)
        if unit.dimension is not dimension:
            raise ValidationError(f"Unit must have {dimension.value} dimension")
        return unit

    @staticmethod
    def _policy(data: InventoryPolicyData) -> ProductInventoryPolicy:
        return ProductInventoryPolicy(batch_expiry_required=data.batch_expiry_required)
