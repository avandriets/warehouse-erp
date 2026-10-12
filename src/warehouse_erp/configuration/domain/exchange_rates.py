import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from warehouse_erp.configuration.domain.entities import Currency
from warehouse_erp.shared.errors import ApplicationError, ValidationError


class ExchangeRateProviderError(ApplicationError):
    pass


@dataclass(frozen=True, kw_only=True)
class ExchangeRate:
    base_code: str
    quote_code: str
    date: date
    rate: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.rate, Decimal) or type(self.date) is not date:
            raise ValidationError("Exchange rates require a decimal value and an observation date")
        if not all(re.fullmatch(r"[A-Z]{3}", code) for code in (self.base_code, self.quote_code)):
            raise ValidationError("Exchange-rate currency codes must contain three letters")
        if (
            not self.rate.is_finite()
            or self.rate <= 0
            or self.rate.adjusted() > 19
            or self.rate.as_tuple().exponent < -18
        ):
            raise ValidationError("Exchange rates must be positive finite decimal values")
        if self.base_code == self.quote_code:
            raise ValidationError("Exchange rates must use different currencies")


@dataclass(frozen=True, kw_only=True)
class CurrencyRateBatch:
    id: UUID
    base_currency_id: UUID
    base_code: str
    source: str
    fetched_at: datetime
    fetched_by: UUID
    rates: tuple[ExchangeRate, ...]
    missing_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        codes = [rate.quote_code for rate in self.rates]
        if len(codes) != len(set(codes)) or any(
            rate.base_code != self.base_code for rate in self.rates
        ):
            raise ValidationError("Exchange-rate batch contains inconsistent currency pairs")


@dataclass(frozen=True, kw_only=True)
class CurrencyRatesOverview:
    base_currency: Currency | None
    settings_version: int
    batch: CurrencyRateBatch | None


class ExchangeRatesProvider(Protocol):
    source: str

    def latest(self, base_code: str, quotes: tuple[str, ...]) -> tuple[ExchangeRate, ...]: ...
