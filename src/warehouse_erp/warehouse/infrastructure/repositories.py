from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_erp.inventory.domain.policies import IssueStrategy, TrackingMode
from warehouse_erp.shared.errors import ConflictError
from warehouse_erp.warehouse.domain.entities import Location, LocationKind, Warehouse
from warehouse_erp.warehouse.infrastructure.models import LocationModel, WarehouseModel


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _warehouse(model: WarehouseModel) -> Warehouse:
    return Warehouse(
        id=UUID(model.id),
        code=model.code,
        name=model.name,
        description=model.description,
        address_storage_enabled=model.address_storage_enabled,
        tracking_mode=TrackingMode(model.tracking_mode),
        issue_strategy=IssueStrategy(model.issue_strategy),
        active=model.active,
        created_at=_utc(model.created_at),
        created_by=UUID(model.created_by),
        updated_at=_utc(model.updated_at),
        updated_by=UUID(model.updated_by),
    )


def _location(model: LocationModel) -> Location:
    return Location(
        id=UUID(model.id),
        warehouse_id=UUID(model.warehouse_id),
        parent_id=UUID(model.parent_id) if model.parent_id else None,
        code=model.code,
        name=model.name,
        kind=LocationKind(model.kind),
        allows_stock=model.allows_stock,
        active=model.active,
        created_at=_utc(model.created_at),
        created_by=UUID(model.created_by),
        updated_at=_utc(model.updated_at),
        updated_by=UUID(model.updated_by),
    )


class SqlAlchemyWarehouseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: Warehouse) -> None:
        self.session.add(self._model(item))

    def save(self, item: Warehouse) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> Warehouse | None:
        model = self.session.get(WarehouseModel, str(item_id))
        return _warehouse(model) if model else None

    def get_by_code(self, code: str) -> Warehouse | None:
        model = self.session.scalar(select(WarehouseModel).where(WarehouseModel.code == code))
        return _warehouse(model) if model else None

    def list(
        self, *, active: bool | None, allowed_ids: frozenset[UUID] | None, limit: int, offset: int
    ) -> list[Warehouse]:
        if allowed_ids is not None and not allowed_ids:
            return []
        statement = select(WarehouseModel).order_by(WarehouseModel.name, WarehouseModel.id)
        if active is not None:
            statement = statement.where(WarehouseModel.active == active)
        if allowed_ids is not None:
            statement = statement.where(WarehouseModel.id.in_(str(item) for item in allowed_ids))
        return [
            _warehouse(row) for row in self.session.scalars(statement.offset(offset).limit(limit))
        ]

    @staticmethod
    def _model(item: Warehouse) -> WarehouseModel:
        return WarehouseModel(
            id=str(item.id),
            code=item.code,
            name=item.name,
            description=item.description,
            address_storage_enabled=item.address_storage_enabled,
            tracking_mode=item.tracking_mode.value,
            issue_strategy=item.issue_strategy.value,
            active=item.active,
            created_at=item.created_at,
            created_by=str(item.created_by),
            updated_at=item.updated_at,
            updated_by=str(item.updated_by),
        )


class SqlAlchemyLocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: Location) -> None:
        self.session.add(self._model(item))

    def save(self, item: Location) -> None:
        self.session.merge(self._model(item))

    def get(self, item_id: UUID) -> Location | None:
        model = self.session.get(LocationModel, str(item_id))
        return _location(model) if model else None

    def get_by_code(self, warehouse_id: UUID, code: str) -> Location | None:
        model = self.session.scalar(
            select(LocationModel).where(
                LocationModel.warehouse_id == str(warehouse_id),
                LocationModel.code == code,
            )
        )
        return _location(model) if model else None

    def list(
        self,
        *,
        warehouse_id: UUID,
        parent_id: UUID | None,
        root_only: bool,
        active: bool | None,
        limit: int,
        offset: int,
    ) -> list[Location]:
        statement = (
            select(LocationModel)
            .where(LocationModel.warehouse_id == str(warehouse_id))
            .order_by(LocationModel.name, LocationModel.id)
        )
        if parent_id is not None:
            statement = statement.where(LocationModel.parent_id == str(parent_id))
        elif root_only:
            statement = statement.where(LocationModel.parent_id.is_(None))
        if active is not None:
            statement = statement.where(LocationModel.active == active)
        return [
            _location(row) for row in self.session.scalars(statement.offset(offset).limit(limit))
        ]

    def has_active_children(self, parent_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(LocationModel.id)
                .where(LocationModel.parent_id == str(parent_id), LocationModel.active.is_(True))
                .limit(1)
            )
            is not None
        )

    def has_active_in_warehouse(self, warehouse_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(LocationModel.id)
                .where(
                    LocationModel.warehouse_id == str(warehouse_id), LocationModel.active.is_(True)
                )
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def _model(item: Location) -> LocationModel:
        return LocationModel(
            id=str(item.id),
            warehouse_id=str(item.warehouse_id),
            parent_id=str(item.parent_id) if item.parent_id else None,
            code=item.code,
            name=item.name,
            kind=item.kind.value,
            allows_stock=item.allows_stock,
            active=item.active,
            created_at=item.created_at,
            created_by=str(item.created_by),
            updated_at=item.updated_at,
            updated_by=str(item.updated_by),
        )


class SqlAlchemyWarehouseUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.warehouses = SqlAlchemyWarehouseRepository(session)
        self.locations = SqlAlchemyLocationRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Warehouse data conflicts with an existing record") from exc

    def rollback(self) -> None:
        self.session.rollback()
