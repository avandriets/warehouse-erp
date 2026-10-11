from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from warehouse_erp.database import get_db_session
from warehouse_erp.identity.api.dependencies import get_current_user, require_permission
from warehouse_erp.identity.domain.entities import CurrentUser, ScopeType, UserStatus
from warehouse_erp.settings.permissions import SettingsPermission
from warehouse_erp.shared.errors import ForbiddenError
from warehouse_erp.warehouse.api.schemas import (
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
)
from warehouse_erp.warehouse.application.service import WarehouseService
from warehouse_erp.warehouse.infrastructure.repositories import SqlAlchemyWarehouseUnitOfWork
from warehouse_erp.warehouse.permissions import WarehousePermission

router = APIRouter(tags=["warehouse"])


def get_warehouse_service(session: Annotated[Session, Depends(get_db_session)]) -> WarehouseService:
    return WarehouseService(SqlAlchemyWarehouseUnitOfWork(session))


Service = Annotated[WarehouseService, Depends(get_warehouse_service)]
Actor = Annotated[CurrentUser, Depends(get_current_user)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


def _access(
    actor: CurrentUser, permission: WarehousePermission, warehouse_id: UUID | None = None
) -> None:
    if actor.status is not UserStatus.ACTIVE:
        raise ForbiddenError("User account is not active")
    if not actor.has_permission(permission, scope_type=ScopeType.WAREHOUSE, scope_id=warehouse_id):
        raise ForbiddenError(f"Permission required: {permission}")


@router.post(
    "/warehouses",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(WarehousePermission.MANAGE))],
)
def create_warehouse(payload: WarehouseCreate, service: Service, actor: Actor) -> object:
    if {"tracking_mode", "issue_strategy", "address_storage_enabled"} & payload.model_fields_set:
        if not actor.has_permission(SettingsPermission.MANAGE):
            raise ForbiddenError("Permission required: settings.manage")
    return service.create_warehouse(**payload.model_dump(), actor_id=actor.user_id)


@router.get("/warehouses", response_model=list[WarehouseResponse])
def list_warehouses(
    service: Service,
    actor: Actor,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    active: bool | None = None,
) -> object:
    if actor.status is not UserStatus.ACTIVE:
        raise ForbiddenError("User account is not active")
    if actor.has_permission(WarehousePermission.READ):
        allowed_ids = None
    else:
        allowed_ids = frozenset(
            grant.scope_id
            for grant in actor.grants
            if grant.permission_code == WarehousePermission.READ
            and grant.scope_type is ScopeType.WAREHOUSE
            and grant.scope_id is not None
        )
        if not allowed_ids:
            raise ForbiddenError(f"Permission required: {WarehousePermission.READ}")
    return service.list_warehouses(
        active=active, allowed_ids=allowed_ids, limit=limit, offset=offset
    )


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
def get_warehouse(warehouse_id: UUID, service: Service, actor: Actor) -> object:
    _access(actor, WarehousePermission.READ, warehouse_id)
    return service.get_warehouse(warehouse_id)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
def update_warehouse(
    warehouse_id: UUID, payload: WarehouseUpdate, service: Service, actor: Actor
) -> object:
    _access(actor, WarehousePermission.MANAGE, warehouse_id)
    if {"tracking_mode", "issue_strategy", "address_storage_enabled"} & payload.model_fields_set:
        if not actor.has_permission(SettingsPermission.MANAGE):
            raise ForbiddenError("Permission required: settings.manage")
    return service.update_warehouse(
        warehouse_id,
        **payload.model_dump(),
        description_set="description" in payload.model_fields_set,
        actor_id=actor.user_id,
    )


@router.post(
    "/warehouses/{warehouse_id}/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location(
    warehouse_id: UUID, payload: LocationCreate, service: Service, actor: Actor
) -> object:
    _access(actor, WarehousePermission.MANAGE, warehouse_id)
    return service.create_location(
        warehouse_id=warehouse_id, **payload.model_dump(), actor_id=actor.user_id
    )


@router.get("/warehouses/{warehouse_id}/locations", response_model=list[LocationResponse])
def list_locations(
    warehouse_id: UUID,
    service: Service,
    actor: Actor,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    parent_id: UUID | None = None,
    root_only: bool = False,
    active: bool | None = None,
) -> object:
    _access(actor, WarehousePermission.READ, warehouse_id)
    return service.list_locations(
        warehouse_id=warehouse_id,
        parent_id=parent_id,
        root_only=root_only,
        active=active,
        limit=limit,
        offset=offset,
    )


@router.get("/locations/{location_id}", response_model=LocationResponse)
def get_location(location_id: UUID, service: Service, actor: Actor) -> object:
    item = service.get_location(location_id)
    _access(actor, WarehousePermission.READ, item.warehouse_id)
    return item


@router.patch("/locations/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: UUID, payload: LocationUpdate, service: Service, actor: Actor
) -> object:
    item = service.get_location(location_id)
    _access(actor, WarehousePermission.MANAGE, item.warehouse_id)
    return service.update_location(
        location_id,
        **payload.model_dump(),
        parent_id_set="parent_id" in payload.model_fields_set,
        actor_id=actor.user_id,
    )
