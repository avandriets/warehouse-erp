from uuid import uuid4

import pytest

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
