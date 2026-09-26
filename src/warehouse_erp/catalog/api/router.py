from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from warehouse_erp.catalog.api.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    InventoryPolicySchema,
    PackageCreate,
    PackageResponse,
    PackageSetCreate,
    PackageSetResponse,
    PackageSetUpdate,
    PackageUpdate,
    ProductBarcodeCreate,
    ProductBarcodeResponse,
    ProductBarcodeUpdate,
    ProductConversionRequest,
    ProductConversionResponse,
    ProductCreate,
    ProductMeasurementCreate,
    ProductMeasurementResponse,
    ProductMeasurementUpdate,
    ProductResponse,
    ProductUpdate,
    UnitConversionRequest,
    UnitConversionResponse,
    UnitCreate,
    UnitResponse,
    UnitUpdate,
)
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
from warehouse_erp.catalog.application.service import CatalogService
from warehouse_erp.catalog.infrastructure.repositories import SqlAlchemyCatalogUnitOfWork
from warehouse_erp.catalog.permissions import CatalogPermission
from warehouse_erp.database import get_db_session
from warehouse_erp.identity.api.dependencies import require_permission

router = APIRouter(prefix="/catalog", tags=["catalog"])


def get_catalog_service(session: Annotated[Session, Depends(get_db_session)]) -> CatalogService:
    return CatalogService(SqlAlchemyCatalogUnitOfWork(session))


Service = Annotated[CatalogService, Depends(get_catalog_service)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_category(payload: CategoryCreate, service: Service) -> object:
    return service.create_category(CreateCategory(**payload.model_dump()))


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_categories(
    service: Service,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    active: bool | None = None,
    parent_id: UUID | None = None,
    root_only: bool = False,
) -> object:
    return service.list_categories(
        limit=limit,
        offset=offset,
        active=active,
        parent_id=parent_id,
        root_only=root_only,
    )


@router.get(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def get_category(category_id: UUID, service: Service) -> object:
    return service.get_category(category_id)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_category(category_id: UUID, payload: CategoryUpdate, service: Service) -> object:
    command = UpdateCategory(
        **payload.model_dump(),
        parent_id_set="parent_id" in payload.model_fields_set,
    )
    return service.update_category(category_id, command)


@router.post(
    "/units",
    response_model=UnitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_unit(payload: UnitCreate, service: Service) -> object:
    return service.create_unit(CreateUnit(**payload.model_dump()))


@router.post(
    "/units/convert",
    response_model=UnitConversionResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def convert_unit(payload: UnitConversionRequest, service: Service) -> object:
    return UnitConversionResponse(
        quantity=service.convert_unit_quantity(**payload.model_dump()),
        unit_id=payload.to_unit_id,
    )


@router.get(
    "/units",
    response_model=list[UnitResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_units(
    service: Service,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    active: bool | None = None,
) -> object:
    return service.list_units(limit=limit, offset=offset, active=active)


@router.get(
    "/units/{unit_id}",
    response_model=UnitResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def get_unit(unit_id: UUID, service: Service) -> object:
    return service.get_unit(unit_id)


@router.patch(
    "/units/{unit_id}",
    response_model=UnitResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_unit(unit_id: UUID, payload: UnitUpdate, service: Service) -> object:
    return service.update_unit(
        unit_id,
        UpdateUnit(
            **payload.model_dump(),
            classifier_code_set="classifier_code" in payload.model_fields_set,
        ),
    )


@router.post(
    "/package-sets",
    response_model=PackageSetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_package_set(payload: PackageSetCreate, service: Service) -> object:
    return service.create_package_set(CreatePackageSet(**payload.model_dump()))


@router.get(
    "/package-sets",
    response_model=list[PackageSetResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_package_sets(
    service: Service, limit: PageLimit = 50, offset: PageOffset = 0, active: bool | None = None
) -> object:
    return service.list_package_sets(limit=limit, offset=offset, active=active)


@router.get(
    "/package-sets/{package_set_id}",
    response_model=PackageSetResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def get_package_set(package_set_id: UUID, service: Service) -> object:
    return service.get_package_set(package_set_id)


@router.patch(
    "/package-sets/{package_set_id}",
    response_model=PackageSetResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_package_set(package_set_id: UUID, payload: PackageSetUpdate, service: Service) -> object:
    return service.update_package_set(package_set_id, UpdatePackageSet(**payload.model_dump()))


@router.post(
    "/package-sets/{package_set_id}/packages",
    response_model=PackageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_package(package_set_id: UUID, payload: PackageCreate, service: Service) -> object:
    return service.create_package(
        CreatePackage(package_set_id=package_set_id, **payload.model_dump())
    )


@router.get(
    "/package-sets/{package_set_id}/packages",
    response_model=list[PackageResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_packages(package_set_id: UUID, service: Service, active: bool | None = None) -> object:
    return service.list_packages(package_set_id, active=active)


@router.get(
    "/packages/{package_id}",
    response_model=PackageResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def get_package(package_id: UUID, service: Service) -> object:
    return service.get_package(package_id)


@router.patch(
    "/packages/{package_id}",
    response_model=PackageResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_package(package_id: UUID, payload: PackageUpdate, service: Service) -> object:
    return service.update_package(
        package_id,
        UpdatePackage(
            **payload.model_dump(),
            contains_package_id_set="contains_package_id" in payload.model_fields_set,
            contains_unit_id_set="contains_unit_id" in payload.model_fields_set,
        ),
    )


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_product(payload: ProductCreate, service: Service) -> object:
    data = payload.model_dump(exclude={"policy"})
    return service.create_product(CreateProduct(**data, policy=_policy(payload.policy)))


@router.get(
    "/products",
    response_model=list[ProductResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_products(
    service: Service,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    active: bool | None = None,
    category_id: UUID | None = None,
) -> object:
    return service.list_products(limit=limit, offset=offset, active=active, category_id=category_id)


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def get_product(product_id: UUID, service: Service) -> object:
    return service.get_product(product_id)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_product(product_id: UUID, payload: ProductUpdate, service: Service) -> object:
    data = payload.model_dump(exclude={"policy"})
    policy = _policy(payload.policy) if payload.policy is not None else None
    return service.update_product(
        product_id,
        UpdateProduct(
            **data,
            policy=policy,
            package_set_id_set="package_set_id" in payload.model_fields_set,
        ),
    )


@router.post(
    "/products/{product_id}/measurements",
    response_model=ProductMeasurementResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_measurement(
    product_id: UUID, payload: ProductMeasurementCreate, service: Service
) -> object:
    return service.create_measurement(
        CreateProductMeasurement(product_id=product_id, **payload.model_dump())
    )


@router.get(
    "/products/{product_id}/measurements",
    response_model=list[ProductMeasurementResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_measurements(product_id: UUID, service: Service, active: bool | None = None) -> object:
    return service.list_measurements(product_id, active=active)


@router.patch(
    "/products/{product_id}/measurements/{measurement_id}",
    response_model=ProductMeasurementResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_measurement(
    product_id: UUID, measurement_id: UUID, payload: ProductMeasurementUpdate, service: Service
) -> object:
    return service.update_measurement(
        product_id, measurement_id, UpdateProductMeasurement(**payload.model_dump())
    )


@router.post(
    "/products/{product_id}/barcodes",
    response_model=ProductBarcodeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(CatalogPermission.CREATE))],
)
def create_barcode(product_id: UUID, payload: ProductBarcodeCreate, service: Service) -> object:
    return service.create_barcode(
        CreateProductBarcode(product_id=product_id, **payload.model_dump())
    )


@router.get(
    "/products/{product_id}/barcodes",
    response_model=list[ProductBarcodeResponse],
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def list_barcodes(product_id: UUID, service: Service, active: bool | None = None) -> object:
    return service.list_barcodes(product_id, active=active)


@router.patch(
    "/products/{product_id}/barcodes/{barcode_id}",
    response_model=ProductBarcodeResponse,
    dependencies=[Depends(require_permission(CatalogPermission.EDIT))],
)
def update_barcode(
    product_id: UUID, barcode_id: UUID, payload: ProductBarcodeUpdate, service: Service
) -> object:
    return service.update_barcode(
        product_id, barcode_id, UpdateProductBarcode(**payload.model_dump())
    )


@router.post(
    "/products/{product_id}/convert",
    response_model=ProductConversionResponse,
    dependencies=[Depends(require_permission(CatalogPermission.READ))],
)
def convert_product(
    product_id: UUID, payload: ProductConversionRequest, service: Service
) -> object:
    storage_quantity = service.convert_to_storage(product_id, **payload.model_dump())
    return ProductConversionResponse(
        storage_unit_id=service.get_product(product_id).storage_unit_id,
        storage_quantity=storage_quantity,
        factor=storage_quantity / payload.quantity,
    )


def _policy(payload: InventoryPolicySchema) -> InventoryPolicyData:
    return InventoryPolicyData(**payload.model_dump())
