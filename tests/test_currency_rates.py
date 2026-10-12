from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock
from urllib.error import URLError
from uuid import uuid4

import pytest
from conftest import ADMIN_USER_ID
from sqlalchemy import func, select

from warehouse_erp.configuration.application.currency_rates import CurrencyRatesService
from warehouse_erp.configuration.application.service import settings_id
from warehouse_erp.configuration.domain.entities import AccountingSettings, Currency
from warehouse_erp.configuration.domain.exchange_rates import (
    CurrencyRateBatch,
    ExchangeRate,
    ExchangeRateProviderError,
)
from warehouse_erp.configuration.infrastructure.exchange_rates import (
    FrankfurterExchangeRatesProvider,
)
from warehouse_erp.configuration.infrastructure.models import CurrencyRateBatchModel
from warehouse_erp.identity.api.dependencies import get_current_user
from warehouse_erp.shared.errors import ConflictError, ValidationError


def rate(value="1.123456789012345678", quote="USD"):
    return ExchangeRate(
        base_code="EUR", quote_code=quote, date=date(2026, 10, 9), rate=Decimal(value)
    )


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e20", "1e-19"])
def test_rate_rejects_invalid_decimal_values(value):
    with pytest.raises(ValidationError):
        rate(value)


def test_batch_rejects_duplicate_or_mixed_pairs():
    values = dict(
        id=uuid4(),
        base_currency_id=uuid4(),
        base_code="EUR",
        source="test",
        fetched_at=datetime.now(UTC),
        fetched_by=uuid4(),
        missing_codes=(),
    )
    with pytest.raises(ValidationError):
        CurrencyRateBatch(**values, rates=(rate(), rate()))
    with pytest.raises(ValidationError):
        CurrencyRateBatch(**values, rates=(replace(rate(), base_code="GBP"),))


def test_provider_keeps_decimal_precision_and_filters_to_configured_quotes(monkeypatch):
    raw = (
        b'[{"base":"EUR","quote":"USD","date":"2026-10-09",'
        b'"rate":1.123456789012345678},'
        b'{"base":"EUR","quote":"GBP","date":"2026-10-09","rate":0.8}]'
    )
    opener = Mock(return_value=BytesIO(raw))
    monkeypatch.setattr("warehouse_erp.configuration.infrastructure.exchange_rates.urlopen", opener)
    result = FrankfurterExchangeRatesProvider().latest("EUR", ("USD", "AAA"))
    assert result == (rate(),)
    assert "base=EUR" in opener.call_args.args[0].full_url
    assert opener.call_args.kwargs["timeout"] == 15


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b"not JSON",
        b'[{"base":"GBP","quote":"USD"}]',
        b'[{"base":"EUR","quote":"USD","date":"2026-10-09","rate":"NaN"}]',
        b'[{"base":"EUR","quote":"USD","date":"2026-10-09","rate":"broken"}]',
    ],
)
def test_provider_wraps_malformed_data_as_recoverable_failure(monkeypatch, payload):
    monkeypatch.setattr(
        "warehouse_erp.configuration.infrastructure.exchange_rates.urlopen",
        lambda *args, **kwargs: BytesIO(payload),
    )
    with pytest.raises(ExchangeRateProviderError):
        FrankfurterExchangeRatesProvider().latest("EUR", ("USD",))


def test_provider_network_failure_is_safe(monkeypatch):
    opener = Mock(side_effect=URLError("private connection data"))
    monkeypatch.setattr("warehouse_erp.configuration.infrastructure.exchange_rates.urlopen", opener)
    with pytest.raises(ExchangeRateProviderError, match="Previously loaded rates") as error:
        FrankfurterExchangeRatesProvider().latest("EUR", ("USD",))
    assert "private" not in str(error.value)


def test_base_change_during_download_cannot_save_a_batch():
    eur = Currency(code="EUR", name="Euro", symbol="€")
    usd = Currency(code="USD", name="Dollar", symbol="$")
    uow = Mock()
    settings = AccountingSettings(id=settings_id("accounting"), currency_id=eur.id)
    uow.records.get.side_effect = [
        settings,
        eur,
        replace(settings, currency_id=usd.id, version=2),
        usd,
    ]
    uow.records.active_currencies.return_value = [eur, usd]
    uow.records.latest_currency_rates.return_value = None
    provider = Mock(source="test")
    provider.latest.return_value = (rate(),)
    with pytest.raises(ConflictError):
        CurrencyRatesService(uow, provider).load(eur.id, 1, uuid4())
    uow.records.save_currency_rates.assert_not_called()
    uow.commit.assert_not_called()


def test_currency_rates_api_persists_snapshots_and_preserves_them_on_failure(
    client, session_factory, monkeypatch
):
    path = "/api/reference-data/currency-rates"
    provider = Mock(source="Frankfurter")
    provider.latest.return_value = (rate(),)
    monkeypatch.setattr(
        "warehouse_erp.configuration.api.router.FrankfurterExchangeRatesProvider", lambda: provider
    )
    initial = client.get(path).json()
    assert initial == {"base_currency": None, "settings_version": 1, "batch": None}

    def create(code, symbol):
        response = client.post(
            "/api/reference-data/currencies", json={"code": code, "name": code, "symbol": symbol}
        )
        assert response.status_code == 201
        return response.json()

    eur, usd, missing = create("EUR", "€"), create("USD", "$"), create("AAA", "A")
    selected = client.patch(
        path + "/base-currency", json={"currency_id": eur["id"], "expected_version": 1}
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["settings_version"] == 2
    assert client.get("/api/settings/accounting").json()["currency_id"] == eur["id"]
    request = {"base_currency_id": eur["id"], "expected_version": 2}
    assert client.post(path + "/load", json={**request, "expected_version": 1}).status_code == 409
    provider.latest.assert_not_called()
    loaded = client.post(path + "/load", json=request)
    assert loaded.status_code == 200, loaded.text
    batch = loaded.json()["batch"]
    assert batch["rates"][0]["rate"] == "1.123456789012345678"
    assert batch["rates"][0]["date"] == "2026-10-09"
    assert batch["base_currency_id"] == eur["id"]
    assert batch["missing_codes"] == [missing["code"]]
    assert batch["fetched_by"] == str(ADMIN_USER_ID)
    provider.latest.side_effect = ExchangeRateProviderError(
        "Provider unavailable; previous rates kept"
    )
    assert client.post(path + "/load", json=request).status_code == 503
    assert client.get(path).json()["batch"] == batch
    assert (
        client.patch(
            "/api/reference-data/currencies/" + eur["id"],
            json={"active": False, "expected_version": 1},
        ).status_code
        == 409
    )
    provider.latest.side_effect = None
    assert client.post(path + "/load", json=request).status_code == 200
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(CurrencyRateBatchModel)) == 2
    changed = client.patch(
        path + "/base-currency", json={"currency_id": usd["id"], "expected_version": 2}
    )
    assert changed.status_code == 200
    assert changed.json()["batch"] is None
    back = client.patch(
        path + "/base-currency", json={"currency_id": eur["id"], "expected_version": 3}
    )
    assert back.status_code == 200
    assert back.json()["batch"]["base_currency_id"] == eur["id"]
    assert client.get("/api/reference-data/currencies", params={"limit": 1}).json()["total"] == 3
    user = client.app.dependency_overrides[get_current_user]()
    client.app.dependency_overrides[get_current_user] = lambda: replace(
        user,
        grants=tuple(grant for grant in user.grants if grant.permission_code != "settings.manage"),
    )
    assert client.get(path).status_code == 200
    assert (
        client.post(
            path + "/load", json={"base_currency_id": eur["id"], "expected_version": 4}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            path + "/base-currency", json={"currency_id": usd["id"], "expected_version": 4}
        ).status_code
        == 403
    )
