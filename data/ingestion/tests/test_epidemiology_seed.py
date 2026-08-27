"""The seeded epidemiology baseline.

Prevalence was supplied only by the live WHO fetch, so a container brought up
with `--seed-only` had an empty table and could not run a scenario at all —
every run failed on `epidemiology.prevalence` before reaching the engine.

The blank-interval case has its own test because of how it failed. The source
file carries no confidence interval, `_read` turns a blank field into `pd.NA`,
and `float(pd.NA)` is `nan` — which reaches PostgreSQL as a real value and
violates the interval CHECK constraint. It only appears against an empty
database: once a row exists the publisher updates it instead of inserting, so
a second `docker compose up` looked fine and a first one on a clean volume did
not.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest
from biet_api.models import Country, Epidemiology, Indication
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import TARGET_COUNTRIES
from ..publish.seed import publish_epidemiology

_HEADER = [
    "country_code", "indication_id", "year", "prevalence_pct", "prevalence_low",
    "prevalence_high", "age_group", "sex", "source", "confidence_tier", "is_projected",
]


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    for model in (Country, Indication, Epidemiology):
        model.__table__.create(engine)
    with Session(engine) as s:
        s.add(Country(country_code="DEU", country_name="Germany", currency_code="EUR",
                      region="Europe", health_system_type="social_insurance_bismarck"))
        s.add(Indication(indication_id=1, indication_name="Obesity",
                         therapy_area="obesity", icd10="E66",
                         who_indicator_code="NCD_BMI_30A"))
        s.commit()
        yield s


def _write(directory: Path, low: str, high: str) -> None:
    with (directory / "epidemiology.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_HEADER)
        w.writerow(["DEU", 1, 2024, 25.7, low, high,
                    "AGEGROUP_YEARS18-PLUS", "SEX_BTSX", "WHO GHO", "A", "false"])


@pytest.fixture
def seed_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "seed_dir", tmp_path)
    return tmp_path


def test_a_blank_interval_is_absent_rather_than_nan(
    session: Session, seed_dir: Path,
) -> None:
    """The bug this file exists for. NaN is a value; blank is the absence of one."""
    _write(seed_dir, "", "")

    assert publish_epidemiology(session) == 1
    session.commit()

    row = session.execute(select(Epidemiology)).scalar_one()
    assert row.prevalence_low is None, "a blank bound must be NULL, not NaN"
    assert row.prevalence_high is None
    assert not math.isnan(float(row.prevalence_pct))


def test_a_supplied_interval_is_kept(session: Session, seed_dir: Path) -> None:
    """M9 parameterises the PSA from these; dropping them would be a defect."""
    _write(seed_dir, "22.4", "29.1")

    publish_epidemiology(session)
    session.commit()

    row = session.execute(select(Epidemiology)).scalar_one()
    assert float(row.prevalence_low) == pytest.approx(22.4)
    assert float(row.prevalence_high) == pytest.approx(29.1)


def test_the_shipped_file_covers_every_target_market() -> None:
    """A market carried with no prevalence cannot produce a budget impact."""
    rows = list(csv.DictReader(open("data/seed/epidemiology.csv")))
    covered = {r["country_code"] for r in rows if r["indication_id"] == "1"}

    assert not set(TARGET_COUNTRIES) - covered, (
        f"no obesity prevalence seeded for {sorted(set(TARGET_COUNTRIES) - covered)}"
    )
    assert not covered - set(TARGET_COUNTRIES), (
        f"prevalence seeded for markets that are not targets: "
        f"{sorted(covered - set(TARGET_COUNTRIES))}"
    )


def test_a_market_outside_the_target_set_is_skipped(
    session: Session, seed_dir: Path,
) -> None:
    with (seed_dir / "epidemiology.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_HEADER)
        w.writerow(["ZZZ", 1, 2024, 25.7, "", "",
                    "AGEGROUP_YEARS18-PLUS", "SEX_BTSX", "WHO GHO", "A", "false"])

    assert publish_epidemiology(session) == 0
