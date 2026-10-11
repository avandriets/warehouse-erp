from uuid import uuid4

import pytest

from warehouse_erp.inventory.domain.policies import (
    IssueStrategy,
    TrackingMode,
    WarehouseInventoryPolicy,
)
from warehouse_erp.shared.errors import ValidationError
from warehouse_erp.warehouse.domain.entities import Location, LocationKind, Warehouse


def test_warehouse_and_location_codes_are_stable_normalized_identifiers() -> None:
    warehouse = Warehouse(code=" main ", name=" Main ")
    location = Location(
        warehouse_id=warehouse.id,
        code=" a-01 ",
        name=" Bin A-01 ",
        kind=LocationKind.BIN,
    )
    assert warehouse.code == "MAIN"
    assert warehouse.name == "Main"
    assert location.code == "A-01"
    assert location.name == "Bin A-01"


def test_empty_location_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="name"):
        Location(warehouse_id=uuid4(), code="A", name=" ", kind=LocationKind.ZONE)


@pytest.mark.parametrize("strategy", [IssueStrategy.FIFO, IssueStrategy.FEFO])
def test_automatic_allocation_requires_batch_warehouse(strategy: IssueStrategy) -> None:
    with pytest.raises(ValidationError, match="BATCH"):
        Warehouse(code="A", name="A", issue_strategy=strategy)


@pytest.mark.parametrize(
    "source,destination",
    [
        (TrackingMode.NONE, TrackingMode.BATCH),
        (TrackingMode.BATCH, TrackingMode.NONE),
    ],
)
def test_cross_mode_transfers_rejected(source: TrackingMode, destination: TrackingMode) -> None:
    with pytest.raises(ValidationError, match="Transfers"):
        WarehouseInventoryPolicy(source).validate_transfer_to(WarehouseInventoryPolicy(destination))


@pytest.mark.parametrize("mode", list(TrackingMode))
def test_same_mode_transfers_allowed(mode: TrackingMode) -> None:
    WarehouseInventoryPolicy(mode).validate_transfer_to(WarehouseInventoryPolicy(mode))


def test_expiry_required_product_requires_batch_warehouse() -> None:
    with pytest.raises(ValidationError, match="expiry"):
        WarehouseInventoryPolicy().validate_product(batch_expiry_required=True)
    WarehouseInventoryPolicy(TrackingMode.BATCH).validate_product(batch_expiry_required=True)
