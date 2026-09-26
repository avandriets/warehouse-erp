from decimal import Decimal
from fractions import Fraction

from warehouse_erp.shared.errors import ValidationError

MAX_QUANTITY = 10**15  # NUMERIC(24, 9): fifteen integral digits.


def validate_quantity(quantity: Decimal) -> None:
    if not quantity.is_finite() or not 0 < quantity < MAX_QUANTITY:
        raise ValidationError("Quantity must be positive and less than 10^15")
    if (Fraction(quantity) * 10**9).denominator != 1:
        raise ValidationError("Quantity must have at most 9 decimal places")


def exact_decimal(value: Fraction) -> Decimal:
    """Convert a terminating ratio without ambient Decimal context rounding."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise ValidationError("Quantity has no exact decimal representation")
    scale = max(twos, fives)
    integer = value.numerator * 2 ** (scale - twos) * 5 ** (scale - fives)
    return Decimal((int(integer < 0), tuple(map(int, str(abs(integer)))), -scale))


def storage_quantity(value: Fraction, precision: int) -> Decimal:
    if not 0 < value < MAX_QUANTITY:
        raise ValidationError("Converted quantity must be positive and less than 10^15")
    if (value * 10**precision).denominator != 1:
        raise ValidationError("Converted quantity exceeds target unit precision")
    return exact_decimal(value)
