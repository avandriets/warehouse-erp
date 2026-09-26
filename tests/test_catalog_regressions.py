from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from warehouse_erp.catalog.application.commands import (
    CreateCategory,
    CreatePackage,
    CreatePackageSet,
    CreateProduct,
    CreateProductBarcode,
    CreateUnit,
    UpdateCategory,
    UpdateProduct,
    UpdateProductBarcode,
)
from warehouse_erp.catalog.application.service import CatalogService
from warehouse_erp.catalog.domain.entities import PackageSetKind, UnitDimension
from warehouse_erp.catalog.infrastructure.repositories import SqlAlchemyCatalogUnitOfWork
from warehouse_erp.shared.errors import ConflictError, ValidationError


def test_concurrent_individual_package_ownership(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        service = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
        category = service.create_category(CreateCategory(code="C", name="Category"))
        unit = service.create_unit(
            CreateUnit(
                code="PCS", name="Pieces", symbol="pcs", dimension=UnitDimension.COUNT, precision=0
            )
        )
        package_set = service.create_package_set(
            CreatePackageSet(code="SET", name="Individual", kind=PackageSetKind.INDIVIDUAL)
        )
    barrier = Barrier(2)

    def create(code: str) -> str:
        with session_factory() as session:
            uow = SqlAlchemyCatalogUnitOfWork(session)
            original_lock = uow.package_sets.lock

            def lock(item_id: UUID) -> None:
                # Both transactions have read the old snapshot before either obtains the lock.
                barrier.wait(timeout=30)
                original_lock(item_id)

            uow.package_sets.lock = lock
            try:
                CatalogService(uow).create_product(
                    CreateProduct(
                        code=code,
                        name=code,
                        category_id=category.id,
                        storage_unit_id=unit.id,
                        package_set_id=package_set.id,
                    )
                )
                return "created"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, ["P1", "P2"]))
    assert sorted(outcomes) == ["conflict", "created"]
    with session_factory() as session:
        products = SqlAlchemyCatalogUnitOfWork(session).products.list_by_package_set(package_set.id)
        assert len(products) == 1


def test_concurrent_category_moves_cannot_create_cycle(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
        a = service.create_category(CreateCategory(code="A", name="A"))
        b = service.create_category(CreateCategory(code="B", name="B"))
    barrier = Barrier(2)

    def move(pair: tuple[UUID, UUID]) -> str:
        item_id, parent_id = pair
        with session_factory() as session:
            uow = SqlAlchemyCatalogUnitOfWork(session)
            # Establish an old snapshot, as authentication may do before the use case starts.
            uow.categories.get(item_id)
            uow.categories.get(parent_id)
            barrier.wait(timeout=30)
            try:
                CatalogService(uow).update_category(
                    item_id,
                    UpdateCategory(
                        parent_id=parent_id,
                        parent_id_set=True,
                    ),
                )
                return "moved"
            except ValidationError:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(move, [(a.id, b.id), (b.id, a.id)]))
    assert sorted(outcomes) == ["moved", "rejected"]
    with session_factory() as session:
        repo = SqlAlchemyCatalogUnitOfWork(session).categories
        assert not (repo.get(a.id).parent_id == b.id and repo.get(b.id).parent_id == a.id)


def test_package_barcode_blocks_detachment_and_invalid_reactivation(client: TestClient) -> None:
    def create(path: str, **payload) -> dict:
        response = client.post(f"/api/catalog/{path}", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    category = create("categories", code="C", name="Category")
    unit = create("units", code="PCS", name="Pieces", symbol="pcs", dimension="COUNT", precision=0)
    package_set = create("package-sets", code="SET", name="Set")
    package = create(
        f"package-sets/{package_set['id']}/packages",
        code="PACK",
        name="Pack",
        unit_id=unit["id"],
        contains_unit_id=unit["id"],
        contains_quantity="10",
    )
    product = create(
        "products",
        code="P",
        name="Product",
        category_id=category["id"],
        storage_unit_id=unit["id"],
        package_set_id=package_set["id"],
    )
    barcode = create(f"products/{product['id']}/barcodes", value="123456", package_id=package["id"])
    path = f"/api/catalog/products/{product['id']}"
    barcode_path = f"{path}/barcodes/{barcode['id']}"
    assert client.patch(path, json={"package_set_id": None}).status_code == 409
    assert client.get(path).json()["package_set_id"] == package_set["id"]
    assert client.patch(path, json={"package_set_id": package_set["id"]}).status_code == 200
    assert client.patch(barcode_path, json={"active": False}).status_code == 200
    assert client.patch(path, json={"package_set_id": None}).status_code == 200
    assert client.patch(barcode_path, json={"active": True}).status_code == 422
    assert client.get(f"{path}/barcodes?active=true").json() == []
    assert client.patch(path, json={"package_set_id": package_set["id"]}).status_code == 200
    assert client.patch(barcode_path, json={"active": True}).status_code == 200

    for quantity in ["1e28", "1.00000000000000000000000000001"]:
        assert client.post(f"{path}/convert", json={"quantity": quantity}).status_code == 422
        assert (
            client.post(
                "/api/catalog/units/convert",
                json={
                    "quantity": quantity,
                    "from_unit_id": unit["id"],
                    "to_unit_id": unit["id"],
                },
            ).status_code
            == 422
        )
    result = client.post(f"{path}/convert", json={"quantity": "2", "package_id": package["id"]})
    assert result.status_code == 200
    assert Decimal(result.json()["storage_quantity"]) == 20
    # Valid input whose conversion exceeds the supported numeric range also returns 422.
    assert (
        client.post(
            f"{path}/convert",
            json={
                "quantity": "999999999999999",
                "package_id": package["id"],
            },
        ).status_code
        == 422
    )


def test_barcode_reactivation_and_detachment_are_serialized(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
        category = service.create_category(CreateCategory(code="C", name="Category"))
        unit = service.create_unit(
            CreateUnit(
                code="PCS",
                name="Pieces",
                symbol="pcs",
                dimension=UnitDimension.COUNT,
                precision=0,
            )
        )
        package_set = service.create_package_set(CreatePackageSet(code="SET", name="Set"))
        package = service.create_package(
            CreatePackage(
                package_set_id=package_set.id,
                code="PACK",
                name="Pack",
                unit_id=unit.id,
                contains_unit_id=unit.id,
                contains_quantity=Decimal(10),
            )
        )
        product = service.create_product(
            CreateProduct(
                code="P",
                name="Product",
                category_id=category.id,
                storage_unit_id=unit.id,
                package_set_id=package_set.id,
            )
        )
        barcode = service.create_barcode(
            CreateProductBarcode(
                product_id=product.id,
                value="123456",
                package_id=package.id,
            )
        )
        service.update_barcode(product.id, barcode.id, UpdateProductBarcode(active=False))
    barrier = Barrier(2)

    def change(action: str) -> str:
        with session_factory() as session:
            uow = SqlAlchemyCatalogUnitOfWork(session)
            uow.products.get(product.id)
            uow.barcodes.get(barcode.id)
            barrier.wait(timeout=30)
            service = CatalogService(uow)
            try:
                if action == "detach":
                    service.update_product(
                        product.id,
                        UpdateProduct(
                            package_set_id=None,
                            package_set_id_set=True,
                        ),
                    )
                else:
                    service.update_barcode(
                        product.id, barcode.id, UpdateProductBarcode(active=True)
                    )
                return action
            except (ConflictError, ValidationError):
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(change, ["detach", "activate"]))
    assert outcomes.count("rejected") == 1
    with session_factory() as session:
        uow = SqlAlchemyCatalogUnitOfWork(session)
        saved_product = uow.products.get(product.id)
        saved_barcode = uow.barcodes.get(barcode.id)
        assert not saved_barcode.active or saved_product.package_set_id == package_set.id


def test_locked_writes_can_restore_values_from_an_older_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
        category = service.create_category(CreateCategory(code="C", name="Category"))
        parent = service.create_category(CreateCategory(code="ROOT", name="Root"))
        unit = service.create_unit(
            CreateUnit(
                code="PCS",
                name="Pieces",
                symbol="pcs",
                dimension=UnitDimension.COUNT,
                precision=0,
            )
        )
        product = service.create_product(
            CreateProduct(
                code="P",
                name="Original",
                category_id=category.id,
                storage_unit_id=unit.id,
            )
        )
        barcode = service.create_barcode(
            CreateProductBarcode(product_id=product.id, value="123456")
        )
    with session_factory() as cs, session_factory() as ps, session_factory() as bs:
        category_uow = SqlAlchemyCatalogUnitOfWork(cs)
        product_uow = SqlAlchemyCatalogUnitOfWork(ps)
        barcode_uow = SqlAlchemyCatalogUnitOfWork(bs)
        assert category_uow.categories.get(category.id).parent_id is None
        assert product_uow.products.get(product.id).name == "Original"
        assert barcode_uow.barcodes.get(barcode.id).active
        with session_factory() as session:
            writer = CatalogService(SqlAlchemyCatalogUnitOfWork(session))
            writer.update_category(
                category.id, UpdateCategory(parent_id=parent.id, parent_id_set=True)
            )
            writer.update_product(product.id, UpdateProduct(name="Changed"))
            writer.update_barcode(product.id, barcode.id, UpdateProductBarcode(active=False))
        CatalogService(category_uow).update_category(
            category.id,
            UpdateCategory(
                parent_id=None,
                parent_id_set=True,
            ),
        )
        CatalogService(product_uow).update_product(product.id, UpdateProduct(name="Original"))
        CatalogService(barcode_uow).update_barcode(
            product.id, barcode.id, UpdateProductBarcode(active=True)
        )
    with session_factory() as session:
        uow = SqlAlchemyCatalogUnitOfWork(session)
        assert uow.categories.get(category.id).parent_id is None
        assert uow.products.get(product.id).name == "Original"
        assert uow.barcodes.get(barcode.id).active
