from uuid import UUID

from warehouse_erp.shared.errors import ConflictError, NotFoundError, ValidationError
from warehouse_erp.warehouse.domain.entities import (
    Location,
    LocationKind,
    Warehouse,
    normalize_code,
    utc_now,
    validate_name,
)
from warehouse_erp.warehouse.domain.repositories import WarehouseUnitOfWork


class WarehouseService:
    def __init__(self, unit_of_work: WarehouseUnitOfWork) -> None:
        self.uow = unit_of_work

    def create_warehouse(
        self, *, code: str, name: str, description: str | None, actor_id: UUID
    ) -> Warehouse:
        normalized = normalize_code(code)
        if self.uow.warehouses.get_by_code(normalized):
            raise ConflictError("Warehouse code already exists")
        item = Warehouse(
            code=normalized,
            name=name,
            description=description,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.uow.warehouses.add(item)
        self.uow.commit()
        return item

    def get_warehouse(self, warehouse_id: UUID) -> Warehouse:
        item = self.uow.warehouses.get(warehouse_id)
        if item is None:
            raise NotFoundError("Warehouse not found")
        return item

    def list_warehouses(
        self, *, active: bool | None, allowed_ids: frozenset[UUID] | None, limit: int, offset: int
    ) -> list[Warehouse]:
        return self.uow.warehouses.list(
            active=active, allowed_ids=allowed_ids, limit=limit, offset=offset
        )

    def update_warehouse(
        self,
        warehouse_id: UUID,
        *,
        name: str | None,
        description: str | None,
        description_set: bool,
        active: bool | None,
        actor_id: UUID,
    ) -> Warehouse:
        item = self.get_warehouse(warehouse_id)
        if name is not None:
            item.name = validate_name(name)
        if description_set:
            item.description = description
        if active is False and item.active and self.uow.locations.has_active_in_warehouse(item.id):
            raise ValidationError("Deactivate active locations before deactivating warehouse")
        if active is not None:
            item.active = active
        item.updated_at = utc_now()
        item.updated_by = actor_id
        self.uow.warehouses.save(item)
        self.uow.commit()
        return item

    def get_location(self, location_id: UUID) -> Location:
        item = self.uow.locations.get(location_id)
        if item is None:
            raise NotFoundError("Location not found")
        return item

    def create_location(
        self,
        *,
        warehouse_id: UUID,
        code: str,
        name: str,
        kind: LocationKind,
        parent_id: UUID | None,
        allows_stock: bool,
        actor_id: UUID,
    ) -> Location:
        warehouse = self.get_warehouse(warehouse_id)
        if not warehouse.active:
            raise ValidationError("Warehouse is inactive")
        normalized = normalize_code(code)
        if self.uow.locations.get_by_code(warehouse_id, normalized):
            raise ConflictError("Location code already exists in warehouse")
        if parent_id is not None:
            self._require_parent(parent_id, warehouse_id)
        item = Location(
            warehouse_id=warehouse_id,
            code=normalized,
            name=name,
            kind=kind,
            parent_id=parent_id,
            allows_stock=allows_stock,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.uow.locations.add(item)
        self.uow.commit()
        return item

    def list_locations(
        self,
        *,
        warehouse_id: UUID,
        parent_id: UUID | None,
        root_only: bool,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> list[Location]:
        self.get_warehouse(warehouse_id)
        if parent_id is not None:
            parent = self.get_location(parent_id)
            if parent.warehouse_id != warehouse_id:
                raise ValidationError("Parent belongs to another warehouse")
        return self.uow.locations.list(
            warehouse_id=warehouse_id,
            parent_id=parent_id,
            root_only=root_only,
            active=active,
            limit=limit,
            offset=offset,
        )

    def update_location(
        self,
        location_id: UUID,
        *,
        name: str | None,
        parent_id: UUID | None,
        parent_id_set: bool,
        kind: LocationKind | None,
        allows_stock: bool | None,
        active: bool | None,
        actor_id: UUID,
    ) -> Location:
        item = self.get_location(location_id)
        if name is not None:
            item.name = validate_name(name)
        if parent_id_set:
            if parent_id is not None:
                self._validate_parent_chain(item, parent_id)
            item.parent_id = parent_id
        if kind is not None:
            item.kind = kind
        if allows_stock is not None:
            item.allows_stock = allows_stock
        if active is False and item.active and self.uow.locations.has_active_children(item.id):
            raise ValidationError("Deactivate active child locations first")
        if active is True:
            if not self.get_warehouse(item.warehouse_id).active:
                raise ValidationError("Warehouse is inactive")
            if item.parent_id is not None:
                self._require_parent(item.parent_id, item.warehouse_id)
        if active is not None:
            item.active = active
        item.updated_at = utc_now()
        item.updated_by = actor_id
        self.uow.locations.save(item)
        self.uow.commit()
        return item

    def _require_parent(self, parent_id: UUID, warehouse_id: UUID) -> Location:
        parent = self.get_location(parent_id)
        if parent.warehouse_id != warehouse_id:
            raise ValidationError("Parent belongs to another warehouse")
        if not parent.active:
            raise ValidationError("Parent location is inactive")
        return parent

    def _validate_parent_chain(self, item: Location, parent_id: UUID) -> None:
        current = self._require_parent(parent_id, item.warehouse_id)
        visited: set[UUID] = set()
        while True:
            if current.id == item.id or current.id in visited:
                raise ValidationError("Location hierarchy cannot contain a cycle")
            visited.add(current.id)
            if current.parent_id is None:
                return
            current = self._require_parent(current.parent_id, item.warehouse_id)
