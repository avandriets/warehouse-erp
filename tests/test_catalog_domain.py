import pytest

from warehouse_erp.catalog.domain.entities import (
    IssueStrategy,
    ProductInventoryPolicy,
    TrackingMode,
    Unit,
    UnitDimension,
)
from warehouse_erp.shared.errors import ValidationError


def test_fefo_requires_batch_tracking() -> None:
    with pytest.raises(ValidationError, match="FEFO"):
        ProductInventoryPolicy(
            tracking_mode=TrackingMode.NONE,
            issue_strategy=IssueStrategy.FEFO,
        )


def test_expiry_requires_batch_tracking() -> None:
    with pytest.raises(ValidationError, match="expiry_required"):
        ProductInventoryPolicy(tracking_mode=TrackingMode.NONE, expiry_required=True)


def test_unit_precision_is_bounded() -> None:
    with pytest.raises(ValidationError, match="precision"):
        Unit(code="PCS", name="Pieces", symbol="pcs", dimension=UnitDimension.COUNT, precision=7)
