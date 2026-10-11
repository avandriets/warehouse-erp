from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from warehouse_erp.configuration.domain.entities import (
    DocumentType,
    PriceEntryMode,
    TaxTreatment,
    ValuationMethod,
)
from warehouse_erp.settings.domain.entities import ValueType


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ExchangeRequest(Payload):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = True


class ExternalMappingRequest(Payload):
    source: str = Field(min_length=1, max_length=128)
    external_id: str = Field(min_length=1, max_length=255)


class UpdatePayload(Payload):
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def reject_nulls(self):
        for name in self.model_fields_set - {"expected_version"}:
            if getattr(self, name) is None and name not in self.nullable_fields:
                raise ValueError(f"{name} cannot be null")
        return self


class RecordResponse(Payload):
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None
    updated_by: UUID | None


class CurrencyCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    symbol: str
    display_decimal_places: int = 2
    rounding_decimal_places: int = 2
    rounding_mode: str = "HALF_UP"


class CurrencyUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    symbol: str | None = None
    display_decimal_places: int | None = None
    rounding_decimal_places: int | None = None
    rounding_mode: str | None = None


class CurrencyResponse(CurrencyCreate, RecordResponse):
    pass


class VatRateCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    treatment: TaxTreatment
    rate: Decimal = Decimal("0")


class VatRateUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    treatment: TaxTreatment | None = None
    rate: Decimal | None = None


class VatRateResponse(VatRateCreate, RecordResponse):
    pass


class StorageAnalyticCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    value_type: ValueType
    required: bool = False
    enabled: bool = False
    options: tuple[str, ...] = ()


class StorageAnalyticUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    value_type: ValueType | None = None
    required: bool | None = None
    enabled: bool | None = None
    options: tuple[str, ...] | None = None


class StorageAnalyticResponse(StorageAnalyticCreate, RecordResponse):
    pass


class StorageAnalyticValueCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    definition_id: UUID
    value: StrictBool | StrictInt | str


class StorageAnalyticValueUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    value: StrictBool | StrictInt | str | None = None


class StorageAnalyticValueResponse(StorageAnalyticValueCreate, RecordResponse):
    pass


class CounterpartyCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    tax_identifier: str | None = None
    registration_identifier: str | None = None
    legal_address: str | None = None
    postal_address: str | None = None
    contact_details: str | None = None
    payment_details: str | None = None
    is_supplier: bool = False
    is_customer: bool = False
    is_other_recipient: bool = False


class CounterpartyUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = {
        "payment_details",
        "registration_identifier",
        "tax_identifier",
        "postal_address",
        "legal_address",
        "contact_details",
    }
    name: str | None = None
    active: bool | None = None
    tax_identifier: str | None = None
    registration_identifier: str | None = None
    legal_address: str | None = None
    postal_address: str | None = None
    contact_details: str | None = None
    payment_details: str | None = None
    is_supplier: bool | None = None
    is_customer: bool | None = None
    is_other_recipient: bool | None = None


class CounterpartyResponse(CounterpartyCreate, RecordResponse):
    pass


class PriceTypeCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    price_entry_mode: PriceEntryMode = PriceEntryMode.TAX_EXCLUSIVE


class PriceTypeUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    price_entry_mode: PriceEntryMode | None = None


class PriceTypeResponse(PriceTypeCreate, RecordResponse):
    pass


class AdjustmentReasonCreate(Payload):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    active: bool = True
    operation: str = "ADJUSTMENT"


class AdjustmentReasonUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    name: str | None = None
    active: bool | None = None
    operation: str | None = None


class AdjustmentReasonResponse(AdjustmentReasonCreate, RecordResponse):
    pass


class EnterpriseSettingsCreate(Payload):
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


class EnterpriseSettingsUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = {
        "payment_details",
        "registration_identifier",
        "tax_identifier",
        "logo_url",
        "postal_address",
        "legal_address",
        "contact_details",
    }
    legal_name: str | None = None
    display_name: str | None = None
    tax_identifier: str | None = None
    tax_identifier_label: str | None = None
    registration_identifier: str | None = None
    registration_identifier_label: str | None = None
    legal_address: str | None = None
    postal_address: str | None = None
    contact_details: str | None = None
    payment_details: str | None = None
    logo_url: str | None = None


class EnterpriseSettingsResponse(EnterpriseSettingsCreate, RecordResponse):
    pass


class AccountingSettingsCreate(Payload):
    currency_id: UUID | None = None
    cost_accounting_enabled: bool = False
    cost_valuation_method: ValuationMethod = ValuationMethod.MOVING_WEIGHTED_AVERAGE
    changes_locked_through: date | None = None
    accounting_timezone: str = "UTC"
    vat_enabled: bool = False
    default_vat_rate_id: UUID | None = None
    price_entry_mode: PriceEntryMode = PriceEntryMode.TAX_EXCLUSIVE


class AccountingSettingsUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = {
        "default_vat_rate_id",
        "changes_locked_through",
        "currency_id",
    }
    currency_id: UUID | None = None
    cost_accounting_enabled: bool | None = None
    cost_valuation_method: ValuationMethod | None = None
    changes_locked_through: date | None = None
    accounting_timezone: str | None = None
    vat_enabled: bool | None = None
    default_vat_rate_id: UUID | None = None
    price_entry_mode: PriceEntryMode | None = None


class AccountingSettingsResponse(AccountingSettingsCreate, RecordResponse):
    pass


class DocumentNumberingCreate(Payload):
    document_type: DocumentType
    prefix: str = ""
    numeric_width: int = 6
    reset_annually: bool = True


class DocumentNumberingUpdate(UpdatePayload):
    nullable_fields: ClassVar[set[str]] = set()
    prefix: str | None = None
    numeric_width: int | None = None
    reset_annually: bool | None = None


class DocumentNumberingResponse(DocumentNumberingCreate, RecordResponse):
    pass


DIRECTORY_SCHEMAS = {
    "currencies": (CurrencyCreate, CurrencyUpdate, CurrencyResponse),
    "vat-rates": (VatRateCreate, VatRateUpdate, VatRateResponse),
    "storage-analytics": (StorageAnalyticCreate, StorageAnalyticUpdate, StorageAnalyticResponse),
    "storage-analytic-values": (
        StorageAnalyticValueCreate,
        StorageAnalyticValueUpdate,
        StorageAnalyticValueResponse,
    ),
    "counterparties": (CounterpartyCreate, CounterpartyUpdate, CounterpartyResponse),
    "price-types": (PriceTypeCreate, PriceTypeUpdate, PriceTypeResponse),
    "adjustment-reasons": (
        AdjustmentReasonCreate,
        AdjustmentReasonUpdate,
        AdjustmentReasonResponse,
    ),
}
