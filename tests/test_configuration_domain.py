from decimal import Decimal

import pytest

from warehouse_erp.configuration.domain.entities import (
    AccountingSettings,
    Counterparty,
    Currency,
    DocumentNumbering,
    DocumentType,
    StorageAnalytic,
    StorageAnalyticValue,
    TaxTreatment,
    VatRate,
    validate_analytic_value,
)
from warehouse_erp.settings.domain.entities import ValueType
from warehouse_erp.shared.errors import ValidationError


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(code="EURO", symbol="€"),
        dict(code="EUR", symbol=""),
        dict(code="EUR", symbol="€", rounding_decimal_places=10),
        dict(code="EUR", symbol="€", rounding_mode="UNKNOWN"),
    ],
)
def test_currency_configuration_is_validated(kwargs):
    with pytest.raises(ValidationError):
        Currency(name="Euro", **kwargs)


@pytest.mark.parametrize(
    "treatment,rate",
    [
        (TaxTreatment.TAXABLE, "0"),
        (TaxTreatment.NO_VAT, "20"),
        (TaxTreatment.ZERO_RATE, "5"),
        (TaxTreatment.TAXABLE, "100.01"),
        (TaxTreatment.TAXABLE, "NaN"),
    ],
)
def test_vat_distinguishes_taxable_zero_and_no_vat(treatment, rate):
    with pytest.raises(ValidationError):
        VatRate(code="VAT", name="VAT", treatment=treatment, rate=Decimal(rate))


def test_zero_rate_and_no_vat_remain_distinct():
    zero = VatRate(code="ZERO", name="Zero", treatment=TaxTreatment.ZERO_RATE)
    no_vat = VatRate(code="NONE", name="No VAT", treatment=TaxTreatment.NO_VAT)
    assert zero.rate == no_vat.rate == 0
    assert zero.treatment != no_vat.treatment


def test_analytic_values_are_typed_and_decimal_is_exact():
    definition = StorageAnalytic(code="DENSITY", name="Density", value_type=ValueType.DECIMAL)
    item = StorageAnalyticValue(
        code="VALUE", name="Value", definition_id=definition.id, value="0.1234567890123456789"
    )
    validate_analytic_value(definition, item)
    assert item.value == "0.1234567890123456789"
    integer = StorageAnalytic(code="COUNT", name="Count", value_type=ValueType.INTEGER)
    with pytest.raises(ValidationError):
        validate_analytic_value(
            integer,
            StorageAnalyticValue(code="BOOL", name="Bool", definition_id=integer.id, value=True),
        )


def test_counterparty_requires_role_and_can_have_multiple_roles():
    with pytest.raises(ValidationError):
        Counterparty(code="COMPANY", name="Company")
    party = Counterparty(code="COMPANY", name="Company", is_supplier=True, is_customer=True)
    assert party.is_supplier and party.is_customer


def test_timezone_and_numbering_bounds():
    with pytest.raises(ValidationError):
        AccountingSettings(accounting_timezone="Missing/Zone")
    with pytest.raises(ValidationError):
        DocumentNumbering(document_type=DocumentType.GOODS_RECEIPT, numeric_width=0)
    assert AccountingSettings().cost_valuation_method == "MOVING_WEIGHTED_AVERAGE"
