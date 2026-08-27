"""The seeded FX baseline — the fix for an empty `fx_rates` table.

FX was supplied only by the live Frankfurter fetcher, so a container brought
up with `--seed-only` (deliberately offline, so a first run works with no
internet) started with no rates at all. Every scenario reporting in anything
but USD then failed with "no FX rate for reporting currency 'EUR'; available:
[]" — which reads as a broken install rather than as data never loaded, and
which appeared only under Docker, never on a developer machine that had run a
full ingestion at some point.

The table is created in SQLite here rather than mocked: the publisher's job is
to put rows in a database, and a test that stubbed that out would not have
caught the empty table in the first place.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from biet_api.models import FxRate
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import BASE_CURRENCY, MIN_FX_CURRENCIES, REQUIRED_CURRENCIES
from ..errors import SourceValidationError
from ..publish.seed import publish_fx_rates

_GOOD = [
    ("BRL", "5.1465"), ("CNY", "6.7205"), ("DKK", "6.4065"), ("EUR", "0.85697"),
    ("GBP", "0.73368"), ("INR", "95.42"), ("USD", "1.0"),
]


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    FxRate.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _write(directory: Path, rows: list[tuple[str, str]]) -> None:
    with (directory / "fx_rates.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["currency_code", "rate_per_usd", "fetched_date"])
        for code, rate in rows:
            w.writerow([code, rate, "2026-08-21"])


@pytest.fixture
def seed_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "seed_dir", tmp_path)
    return tmp_path


# ------------------------------------------------------------ the shipped file

def test_the_shipped_seed_covers_every_currency_the_model_can_report_in(
    session: Session,
) -> None:
    """Against `data/seed/fx_rates.csv` as committed, not a fixture."""
    published = publish_fx_rates(session)
    session.commit()

    rates = {
        r.currency_code: float(r.rate_per_usd)
        for r in session.execute(select(FxRate)).scalars()
    }

    assert published >= MIN_FX_CURRENCIES
    assert not REQUIRED_CURRENCIES - set(rates), "a market with no rate cannot report"
    assert rates[BASE_CURRENCY] == 1.0, "M7 pivots conversions through USD"
    assert "EUR" in rates, "the currency in the reported failure"


def test_publishing_twice_supersedes_rather_than_duplicates(session: Session) -> None:
    """`migrate` reruns on every `docker compose up`."""
    first = publish_fx_rates(session)
    session.commit()
    publish_fx_rates(session)
    session.commit()

    assert len(session.execute(select(FxRate)).scalars().all()) == first


# ---------------------------------------------------------------- validation

def test_a_missing_file_is_skipped_rather_than_fatal(
    session: Session, seed_dir: Path,
) -> None:
    """Consistent with every other seed publisher: absent is not corrupt."""
    assert publish_fx_rates(session) == 0


def test_a_missing_currency_is_refused(session: Session, seed_dir: Path) -> None:
    """Better to fail here than at the scenario, further from the cause."""
    _write(seed_dir, [r for r in _GOOD if r[0] != "EUR"])

    with pytest.raises(SourceValidationError, match="EUR"):
        publish_fx_rates(session)


def test_a_non_positive_rate_is_refused(session: Session, seed_dir: Path) -> None:
    _write(seed_dir, [("EUR", "0") if c == "EUR" else (c, r) for c, r in _GOOD])

    with pytest.raises(SourceValidationError, match="non-positive"):
        publish_fx_rates(session)


def test_a_wrong_usd_identity_row_is_refused(session: Session, seed_dir: Path) -> None:
    """Without a 1.0 pivot every conversion needs a special case for USD."""
    _write(seed_dir, [("USD", "1.02") if c == "USD" else (c, r) for c, r in _GOOD])

    with pytest.raises(SourceValidationError, match="identity"):
        publish_fx_rates(session)
