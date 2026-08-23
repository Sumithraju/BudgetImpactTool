"""FX transform rules. No network access."""

import json

import pytest

from data.ingestion.constants import BASE_CURRENCY, MIN_FX_CURRENCIES, REQUIRED_CURRENCIES
from data.ingestion.errors import SourceValidationError
from data.ingestion.sources.frankfurter import FrankfurterFetcher


def test_identity_row_added_for_base_currency(fixtures, monkeypatch):
    fetcher = FrankfurterFetcher()
    monkeypatch.setattr(
        type(fetcher), "raw_path", property(lambda self: fixtures / "frankfurter.json")
    )
    frame = fetcher.transform(fetcher.raw_path)

    usd = frame[frame["currency_code"] == BASE_CURRENCY]
    assert len(usd) == 1
    assert usd["rate_per_usd"].iloc[0] == 1.0


def test_covers_every_market_currency(fixtures, monkeypatch):
    fetcher = FrankfurterFetcher()
    monkeypatch.setattr(
        type(fetcher), "raw_path", property(lambda self: fixtures / "frankfurter.json")
    )
    frame = fetcher.transform(fetcher.raw_path)

    assert REQUIRED_CURRENCIES <= set(frame["currency_code"])
    assert len(frame) >= MIN_FX_CURRENCIES


def test_validate_rejects_missing_currency(tmp_path):
    payload = {"base": "USD", "date": "2026-08-21", "rates": {"EUR": 0.85}}
    path = tmp_path / "fx.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(SourceValidationError):
        FrankfurterFetcher().validate(path)


def test_validate_rejects_missing_date(tmp_path):
    rates = {c: 1.0 for c in REQUIRED_CURRENCIES - {BASE_CURRENCY}}
    path = tmp_path / "fx.json"
    path.write_text(json.dumps({"base": "USD", "rates": rates}))

    with pytest.raises(SourceValidationError):
        FrankfurterFetcher().validate(path)


def test_validate_rejects_non_positive_rate(tmp_path):
    rates = {c: 1.0 for c in REQUIRED_CURRENCIES - {BASE_CURRENCY}}
    rates["EUR"] = 0.0
    path = tmp_path / "fx.json"
    path.write_text(json.dumps({"base": "USD", "date": "2026-08-21", "rates": rates}))

    with pytest.raises(SourceValidationError):
        FrankfurterFetcher().validate(path)
