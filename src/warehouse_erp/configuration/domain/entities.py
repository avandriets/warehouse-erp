"""Typed configuration records. No document posting behavior lives here."""

import re
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from warehouse_erp.catalog.domain.entities import normalize_code, validate_name
from warehouse_erp.settings.domain.entities import ValueType, canonical_value
from warehouse_erp.shared.errors import ValidationError


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class TaxTreatment(StrEnum):
    TAXABLE = "TAXABLE"
    ZERO_RATE = "ZERO_RATE"
    NO_VAT = "NO_VAT"


class PriceEntryMode(StrEnum):
    TAX_INCLUSIVE = "TAX_INCLUSIVE"
    TAX_EXCLUSIVE = "TAX_EXCLUSIVE"


class ValuationMethod(StrEnum):
    MOVING_WEIGHTED_AVERAGE = "MOVING_WEIGHTED_AVERAGE"
    FIFO = "FIFO"


class DocumentType(StrEnum):
    INITIAL_RECEIPT = "INITIAL_RECEIPT"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    GOODS_ISSUE = "GOODS_ISSUE"
    STOCK_TRANSFER = "STOCK_TRANSFER"
    STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
    INVENTORY_COUNT = "INVENTORY_COUNT"
    INBOUND_ORDER = "INBOUND_ORDER"
    OUTBOUND_ORDER = "OUTBOUND_ORDER"
    PRICE_SETTING = "PRICE_SETTING"


@dataclass(kw_only=True)
class Record:
    id: UUID = field(default_factory=uuid4)
    version: int = 1
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
    created_by: UUID | None = None
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, str) and not isinstance(value, StrEnum):
                value = value.strip()
                if len(value) > 4000:
                    raise ValidationError(f"{item.name} is too long")
                setattr(self, item.name, value)


@dataclass(kw_only=True)
class DirectoryRecord(Record):
    code: str
    name: str
    active: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        self.code = normalize_code(self.code)
        self.name = validate_name(self.name)


@dataclass(kw_only=True)
class Currency(DirectoryRecord):
    symbol: str
    display_decimal_places: int = 2
    rounding_decimal_places: int = 2
    rounding_mode: str = "HALF_UP"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not re.fullmatch(r"[A-Z]{3}", self.code):
            raise ValidationError("Currency code must contain three letters")
        if not self.symbol or len(self.symbol) > 32:
            raise ValidationError("Invalid currency symbol")
        if not all(
            0 <= n <= 9 for n in (self.display_decimal_places, self.rounding_decimal_places)
        ):
            raise ValidationError("Currency decimal places must be between 0 and 9")
        if self.rounding_mode not in {"HALF_UP", "HALF_EVEN", "DOWN"}:
            raise ValidationError("Unsupported monetary rounding mode")


@dataclass(kw_only=True)
class VatRate(DirectoryRecord):
    treatment: TaxTreatment
    rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        super().__post_init__()
        self.treatment = TaxTreatment(self.treatment)
        self.rate = Decimal(str(self.rate))
        if not self.rate.is_finite() or not 0 <= self.rate <= 100:
            raise ValidationError("VAT rate must be between 0 and 100")
        if self.rate.as_tuple().exponent < -4:
            raise ValidationError("VAT rate supports at most four decimal places")
        self.rate = self.rate.quantize(Decimal("0.0001"))
        if self.treatment is not TaxTreatment.TAXABLE and self.rate != 0:
            raise ValidationError("No-VAT and zero-rate treatments require rate 0")
        if self.treatment is TaxTreatment.TAXABLE and self.rate == 0:
            raise ValidationError("Use ZERO_RATE or NO_VAT for rate 0")


@dataclass(kw_only=True)
class StorageAnalytic(DirectoryRecord):
    value_type: ValueType
    required: bool = False
    enabled: bool = False
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        self.value_type = ValueType(self.value_type)
        self.options = tuple(self.options)
        if self.value_type is ValueType.ENUM:
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValidationError("ENUM requires nonempty unique options")
        elif self.options:
            raise ValidationError("Only ENUM analytics have options")


@dataclass(kw_only=True)
class StorageAnalyticValue(DirectoryRecord):
    definition_id: UUID
    value: bool | int | str


@dataclass(kw_only=True)
class Counterparty(DirectoryRecord):
    tax_identifier: str | None = None
    registration_identifier: str | None = None
    legal_address: str | None = None
    postal_address: str | None = None
    contact_details: str | None = None
    payment_details: str | None = None
    is_supplier: bool = False
    is_customer: bool = False
    is_other_recipient: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not (self.is_supplier or self.is_customer or self.is_other_recipient):
            raise ValidationError("Select at least one counterparty role")
        for value in (self.tax_identifier, self.registration_identifier):
            if value is not None and len(value) > 128:
                raise ValidationError("Identifier must not exceed 128 characters")


@dataclass(kw_only=True)
class PriceType(DirectoryRecord):
    price_entry_mode: PriceEntryMode = PriceEntryMode.TAX_EXCLUSIVE

    def __post_init__(self) -> None:
        super().__post_init__()
        self.price_entry_mode = PriceEntryMode(self.price_entry_mode)


@dataclass(kw_only=True)
class AdjustmentReason(DirectoryRecord):
    operation: str = "ADJUSTMENT"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.operation not in {"WRITE_OFF", "ADJUSTMENT", "SPOILAGE", "DISPOSAL"}:
            raise ValidationError("Unsupported reason operation")


@dataclass(kw_only=True)
class EnterpriseSettings(Record):
    legal_name: str = ""
    display_name: str = ""
    tax_identifier: str | None = None
    tax_identifier_label: str = "Tax identifier"
    registration_identifier: str | None = None
    registration_identifier_label: str = "Registration identifier"
    legal_address: str | None = None
    postal_address: str | None = None
    contact_details: str | None = None
    payment_details: str | None = None
    logo_url: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.logo_url is not None and not self.logo_url.startswith("https://"):
            raise ValidationError("Logo URL must use HTTPS")
        if any(len(s) > 255 for s in (self.legal_name, self.display_name)):
            raise ValidationError("Enterprise name must not exceed 255 characters")


@dataclass(kw_only=True)
class AccountingSettings(Record):
    currency_id: UUID | None = None
    cost_accounting_enabled: bool = False
    cost_valuation_method: ValuationMethod = ValuationMethod.MOVING_WEIGHTED_AVERAGE
    changes_locked_through: date | None = None
    accounting_timezone: str = "UTC"
    vat_enabled: bool = False
    default_vat_rate_id: UUID | None = None
    price_entry_mode: PriceEntryMode = PriceEntryMode.TAX_EXCLUSIVE

    def __post_init__(self) -> None:
        super().__post_init__()
        self.cost_valuation_method = ValuationMethod(self.cost_valuation_method)
        self.price_entry_mode = PriceEntryMode(self.price_entry_mode)
        try:
            ZoneInfo(self.accounting_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError("Invalid accounting timezone") from exc


@dataclass(kw_only=True)
class DocumentNumbering(Record):
    document_type: DocumentType
    prefix: str = ""
    numeric_width: int = 6
    reset_annually: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        self.document_type = DocumentType(self.document_type)
        if not 1 <= self.numeric_width <= 18 or len(self.prefix) > 32:
            raise ValidationError("Invalid document numbering rule")


DIRECTORIES = {
    "currencies": Currency,
    "vat-rates": VatRate,
    "storage-analytics": StorageAnalytic,
    "storage-analytic-values": StorageAnalyticValue,
    "counterparties": Counterparty,
    "price-types": PriceType,
    "adjustment-reasons": AdjustmentReason,
}
SETTINGS = {"enterprise": EnterpriseSettings, "accounting": AccountingSettings}


def validate_analytic_value(definition: StorageAnalytic, item: StorageAnalyticValue) -> None:
    item.value = canonical_value(item.value, definition.value_type, definition.options)
