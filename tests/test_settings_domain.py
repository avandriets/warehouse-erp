from decimal import Decimal
from uuid import uuid4

import pytest

from warehouse_erp.settings.domain.entities import (
    SettingDefinition,
    SettingsContext,
    SettingScope,
    ValueType,
    canonical_value,
)
from warehouse_erp.shared.errors import ValidationError


def test_scope_precedence_is_explicit() -> None:
    ids = [uuid4() for _ in range(4)]
    context = SettingsContext(
        product_id=ids[0],
        category_id=ids[1],
        warehouse_id=ids[2],
        company_id=ids[3],
    )
    assert [scope for scope, _ in context.candidates()] == [
        SettingScope.PRODUCT,
        SettingScope.CATEGORY,
        SettingScope.WAREHOUSE,
        SettingScope.COMPANY,
        SettingScope.GLOBAL,
    ]


def test_setting_values_are_strictly_typed() -> None:
    assert canonical_value(Decimal("1.250"), ValueType.DECIMAL) == "1.250"
    with pytest.raises(ValidationError, match="integer"):
        canonical_value(True, ValueType.INTEGER)
    with pytest.raises(ValidationError, match="finite"):
        canonical_value("NaN", ValueType.DECIMAL)
    with pytest.raises(ValidationError, match="allowed option"):
        canonical_value("LIFO", ValueType.ENUM, ("FIFO", "FEFO"))


def test_setting_definition_validates_enum_and_required_default() -> None:
    with pytest.raises(ValidationError, match="unique options"):
        SettingDefinition(
            category_id=uuid4(),
            key="test.strategy",
            name="Strategy",
            value_type=ValueType.ENUM,
            default_value="FIFO",
            allowed_scopes=(SettingScope.GLOBAL,),
            options=("FIFO", "FIFO"),
        )
    with pytest.raises(ValidationError, match="default"):
        SettingDefinition(
            category_id=uuid4(),
            key="test.required",
            name="Required",
            value_type=ValueType.BOOLEAN,
            default_value=None,
            allowed_scopes=(SettingScope.GLOBAL,),
        )
