from uuid import UUID, uuid4

from warehouse_erp.configuration.application.service import ConfigurationService, settings_id
from warehouse_erp.configuration.domain.entities import now
from warehouse_erp.configuration.domain.exchange_rates import (
    CurrencyRateBatch,
    CurrencyRatesOverview,
    ExchangeRatesProvider,
)
from warehouse_erp.configuration.domain.repositories import ConfigurationUnitOfWork
from warehouse_erp.shared.errors import ConflictError, ValidationError


class CurrencyRatesService:
    def __init__(self, uow: ConfigurationUnitOfWork, provider: ExchangeRatesProvider) -> None:
        self.uow = uow
        self.configuration = ConfigurationService(uow)
        self.provider = provider

    def overview(self) -> CurrencyRatesOverview:
        accounting = self.configuration.section("accounting")
        base = (
            self.configuration.get("currencies", accounting.currency_id)
            if accounting.currency_id
            else None
        )
        return CurrencyRatesOverview(
            base_currency=base,
            settings_version=accounting.version,
            batch=self.uow.records.latest_currency_rates(base.id) if base else None,
        )

    def set_base(
        self, currency_id: UUID, expected_version: int, actor_id: UUID
    ) -> CurrencyRatesOverview:
        self.configuration.update(
            "accounting",
            settings_id("accounting"),
            {"currency_id": currency_id},
            expected_version,
            actor_id,
        )
        return self.overview()

    def load(
        self, base_currency_id: UUID, expected_version: int, actor_id: UUID
    ) -> CurrencyRatesOverview:
        overview = self.overview()
        base = overview.base_currency
        if base is None:
            raise ValidationError("Select an accounting currency before loading exchange rates")
        if base.id != base_currency_id or overview.settings_version != expected_version:
            raise ConflictError(
                "Accounting settings changed. Reload currencies before loading rates"
            )
        currencies = self.uow.records.active_currencies()
        quotes = tuple(currency.code for currency in currencies if currency.id != base.id)
        if not quotes:
            raise ValidationError("Add another active currency before loading exchange rates")
        rates = self.provider.latest(base.code, quotes)
        if not rates:
            raise ValidationError("The provider has no rates for the configured currencies")
        if len({rate.quote_code for rate in rates}) != len(rates) or any(
            rate.base_code != base.code or rate.quote_code not in quotes for rate in rates
        ):
            raise ValidationError("The provider returned inconsistent currency pairs")
        self.uow.records.lock()
        latest = self.overview()
        current_quotes = tuple(
            currency.code
            for currency in self.uow.records.active_currencies()
            if currency.id != base.id
        )
        if (
            latest.settings_version != expected_version
            or latest.base_currency is None
            or latest.base_currency.id != base.id
            or current_quotes != quotes
        ):
            raise ConflictError(
                "Currencies or accounting settings changed during download. Reload and try again"
            )
        batch = CurrencyRateBatch(
            id=uuid4(),
            base_currency_id=base.id,
            base_code=base.code,
            source=self.provider.source,
            fetched_at=now(),
            fetched_by=actor_id,
            rates=rates,
            missing_codes=tuple(sorted(set(quotes) - {rate.quote_code for rate in rates})),
        )
        self.uow.records.save_currency_rates(batch)
        self.uow.commit()
        return CurrencyRatesOverview(
            base_currency=base, settings_version=expected_version, batch=batch
        )
