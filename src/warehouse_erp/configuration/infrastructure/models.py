from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from warehouse_erp.database import Base


class RecordColumns:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT")
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT")
    )


class CurrencyModel(RecordColumns, Base):
    __tablename__ = "configuration_currencies"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    display_decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    rounding_decimal_places: Mapped[int] = mapped_column(Integer, nullable=False)
    rounding_mode: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_currencies_code"),
        Index("ix_configuration_currencies_name", "active", "name", "id"),
    )


class VatRateModel(RecordColumns, Base):
    __tablename__ = "configuration_vat_rates"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    treatment: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_vat_rates_code"),
        Index("ix_configuration_vat_rates_name", "active", "name", "id"),
    )


class StorageAnalyticModel(RecordColumns, Base):
    __tablename__ = "configuration_storage_analytics"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_storage_analytics_code"),
        Index("ix_configuration_storage_analytics_name", "active", "name", "id"),
    )


class StorageAnalyticValueModel(RecordColumns, Base):
    __tablename__ = "configuration_storage_analytic_values"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    definition_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("configuration_storage_analytics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    value: Mapped[bool | int | str] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "definition_id", "code", name="uq_configuration_storage_analytic_values_code"
        ),
        Index("ix_configuration_storage_analytic_values_name", "active", "name", "id"),
        Index("ix_analytic_values_definition", "definition_id", "active"),
    )


class CounterpartyModel(RecordColumns, Base):
    __tablename__ = "configuration_counterparties"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tax_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_supplier: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_customer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_other_recipient: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_counterparties_code"),
        Index("ix_configuration_counterparties_name", "active", "name", "id"),
        Index("ix_counterparty_tax_identifier", "tax_identifier"),
        Index("ix_counterparty_registration_identifier", "registration_identifier"),
    )


class PriceTypeModel(RecordColumns, Base):
    __tablename__ = "configuration_price_types"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    price_entry_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_price_types_code"),
        Index("ix_configuration_price_types_name", "active", "name", "id"),
    )


class AdjustmentReasonModel(RecordColumns, Base):
    __tablename__ = "configuration_adjustment_reasons"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("code", name="uq_configuration_adjustment_reasons_code"),
        Index("ix_configuration_adjustment_reasons_name", "active", "name", "id"),
    )


class EnterpriseSettingsModel(RecordColumns, Base):
    __tablename__ = "configuration_enterprise"
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    tax_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_identifier_label: Mapped[str] = mapped_column(Text, nullable=False)
    registration_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_identifier_label: Mapped[str] = mapped_column(Text, nullable=False)
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccountingSettingsModel(RecordColumns, Base):
    __tablename__ = "configuration_accounting"
    currency_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("configuration_currencies.id", ondelete="RESTRICT"), nullable=True
    )
    cost_accounting_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_valuation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    changes_locked_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    accounting_timezone: Mapped[str] = mapped_column(String(255), nullable=False)
    vat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_vat_rate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("configuration_vat_rates.id", ondelete="RESTRICT"), nullable=True
    )
    price_entry_mode: Mapped[str] = mapped_column(String(32), nullable=False)


class DocumentNumberingModel(RecordColumns, Base):
    __tablename__ = "configuration_numbering"
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    numeric_width: Mapped[int] = mapped_column(Integer, nullable=False)
    reset_annually: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (UniqueConstraint("document_type", name="uq_numbering_document_type"),)


class ExternalMappingModel(Base):
    __tablename__ = "configuration_external_mappings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255, collation="utf8mb4_bin"), nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("kind", "source", "external_id", name="uq_external_mapping_source"),
        Index("ix_external_mapping_record", "kind", "record_id"),
    )


class ConfigurationGuardModel(Base):
    __tablename__ = "configuration_guard"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class ConfigurationAuditModel(Base):
    __tablename__ = "configuration_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (Index("ix_configuration_audit_record", "kind", "record_id", "changed_at"),)


MODELS = {
    "currencies": CurrencyModel,
    "vat-rates": VatRateModel,
    "storage-analytics": StorageAnalyticModel,
    "storage-analytic-values": StorageAnalyticValueModel,
    "counterparties": CounterpartyModel,
    "price-types": PriceTypeModel,
    "adjustment-reasons": AdjustmentReasonModel,
    "enterprise": EnterpriseSettingsModel,
    "accounting": AccountingSettingsModel,
    "numbering": DocumentNumberingModel,
}
