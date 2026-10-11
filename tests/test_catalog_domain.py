import pytest

from warehouse_erp.catalog.domain.entities import (
    ProductInventoryPolicy,
    Unit,
    UnitDimension,
)
from warehouse_erp.shared.errors import ValidationError


def test_product_expiry_requirement_is_independent_of_warehouse_policy() -> None:
    assert ProductInventoryPolicy(batch_expiry_required=True).batch_expiry_required is True


def test_unit_precision_is_bounded() -> None:
    with pytest.raises(ValidationError, match="precision"):
        Unit(code="PCS", name="Pieces", symbol="pcs", dimension=UnitDimension.COUNT, precision=7)
