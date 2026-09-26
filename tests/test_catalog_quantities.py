from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from warehouse_erp.catalog.domain.quantities import (
    exact_decimal,
    storage_quantity,
    validate_quantity,
)
from warehouse_erp.shared.errors import ValidationError


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e28", "0.0000000001"])
def test_invalid_quantities_raise_domain_validation(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_quantity(Decimal(value))


def test_quantity_conversion_is_independent_of_decimal_context() -> None:
    with localcontext() as context:
        context.prec = 3
        validate_quantity(Decimal("999999999999999.123456789"))
        result = storage_quantity(Fraction(Decimal("123456789.123456")), 6)
        assert result == Decimal("123456789.123456")
        assert exact_decimal(Fraction(1, 10**18)) == Decimal("0.000000000000000001")


@pytest.mark.parametrize(
    "value,precision", [(Fraction(1, 3), 6), (Fraction(1, 2), 0), (Fraction(10**15), 0)]
)
def test_unrepresentable_results_are_rejected(value: Fraction, precision: int) -> None:
    with pytest.raises(ValidationError):
        storage_quantity(value, precision)
