from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from warehouse_erp.database import get_db_session
from warehouse_erp.identity.api.dependencies import get_current_user, require_permission
from warehouse_erp.identity.domain.entities import CurrentUser
from warehouse_erp.settings.api.schemas import (
    CategoryCreate,
    CategoryResponse,
    DefinitionCreate,
    DefinitionResponse,
    InventoryDefaultsResponse,
    ResolvedResponse,
    ValueResponse,
    ValueUpsert,
)
from warehouse_erp.settings.application.service import SettingsService
from warehouse_erp.settings.domain.entities import SettingsContext
from warehouse_erp.settings.infrastructure.repositories import SqlAlchemySettingsUnitOfWork
from warehouse_erp.settings.permissions import SettingsPermission

router = APIRouter(prefix="/settings", tags=["settings"])


def get_settings_service(session: Annotated[Session, Depends(get_db_session)]) -> SettingsService:
    return SettingsService(SqlAlchemySettingsUnitOfWork(session))


Service = Annotated[SettingsService, Depends(get_settings_service)]
Actor = Annotated[CurrentUser, Depends(get_current_user)]


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def create_category(payload: CategoryCreate, service: Service) -> object:
    return service.create_category(payload.code, payload.name)


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def list_categories(service: Service) -> object:
    return service.list_categories()


@router.post(
    "/definitions",
    response_model=DefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def create_definition(payload: DefinitionCreate, service: Service) -> object:
    return service.create_definition(**payload.model_dump())


@router.get(
    "/definitions",
    response_model=list[DefinitionResponse],
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def list_definitions(service: Service, category_id: UUID | None = None) -> object:
    return service.list_definitions(category_id)


@router.get(
    "/definitions/{key}",
    response_model=DefinitionResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def get_definition(key: str, service: Service) -> object:
    return service.get_definition(key)


@router.get(
    "/definitions/{key}/values",
    response_model=list[ValueResponse],
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def list_values(key: str, service: Service) -> object:
    return service.list_values(key)


@router.put(
    "/definitions/{key}/values",
    response_model=ValueResponse,
    dependencies=[Depends(require_permission(SettingsPermission.MANAGE))],
)
def set_value(key: str, payload: ValueUpsert, service: Service, actor: Actor) -> object:
    return service.set_value(key=key, actor_id=actor.user_id, **payload.model_dump())


def _context(
    company_id: UUID | None,
    warehouse_id: UUID | None,
    category_id: UUID | None,
    product_id: UUID | None,
) -> SettingsContext:
    return SettingsContext(
        company_id=company_id,
        warehouse_id=warehouse_id,
        category_id=category_id,
        product_id=product_id,
    )


@router.get(
    "/resolve/{key}",
    response_model=ResolvedResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def resolve_setting(
    key: str,
    service: Service,
    company_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    category_id: UUID | None = None,
    product_id: UUID | None = None,
) -> object:
    return service.resolve(key, _context(company_id, warehouse_id, category_id, product_id))


@router.get(
    "/inventory-defaults",
    response_model=InventoryDefaultsResponse,
    dependencies=[Depends(require_permission(SettingsPermission.READ))],
)
def resolve_inventory_defaults(
    service: Service,
    company_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    category_id: UUID | None = None,
    product_id: UUID | None = None,
) -> object:
    return service.resolve_inventory_defaults(
        _context(company_id, warehouse_id, category_id, product_id)
    )
