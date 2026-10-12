import json
import ssl
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

from warehouse_erp.configuration.domain.exchange_rates import (
    ExchangeRate,
    ExchangeRateProviderError,
)
from warehouse_erp.shared.errors import ValidationError


class FrankfurterExchangeRatesProvider:
    source = "Frankfurter"

    def latest(self, base_code: str, quotes: tuple[str, ...]) -> tuple[ExchangeRate, ...]:
        request = Request(
            "https://api.frankfurter.dev/v2/rates?" + urlencode({"base": base_code}),
            headers={"Accept": "application/json", "User-Agent": "WarehouseERP/0.1"},
        )
        try:
            with urlopen(
                request, timeout=15, context=ssl.create_default_context(cafile=certifi.where())
            ) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Response too large")
            payload = json.loads(raw, parse_float=Decimal)
            if not isinstance(payload, list):
                raise ValueError("Invalid rate response")
            result = []
            for row in payload:
                if row["base"] != base_code or not isinstance(row["quote"], str):
                    raise ValueError("Invalid currency pair")
                if row["quote"] not in quotes:
                    continue
                result.append(
                    ExchangeRate(
                        base_code=base_code,
                        quote_code=row["quote"],
                        date=date.fromisoformat(row["date"]),
                        rate=Decimal(str(row["rate"])),
                    )
                )
            return tuple(result)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            InvalidOperation,
            KeyError,
            TypeError,
            ValidationError,
        ) as exc:
            raise ExchangeRateProviderError(
                "Exchange-rate provider is unavailable or returned invalid data. "
                "Previously loaded rates have been kept."
            ) from exc
