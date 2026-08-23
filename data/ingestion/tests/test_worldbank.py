"""World Bank transform rules. No network access."""

import pytest

from data.ingestion.errors import CoverageError, MissingValueError
from data.ingestion.sources.worldbank import (
    WorldBankFetcher,
    build_countries,
    derive_adult_share,
    latest_non_null,
)


def _rows(*triples):
    return [
        {"countryiso3code": c, "date": str(y), "value": v, "indicator": {"id": "IND"}}
        for c, y, v in triples
    ]


class TestLatestNonNull:
    def test_skips_null_years_and_picks_most_recent_populated(self):
        rows = _rows(("DEU", 2025, None), ("DEU", 2023, 6849.0), ("DEU", 2024, None))
        assert latest_non_null(rows, "DEU", "IND") == (2023, 6849.0)

    def test_prefers_later_year_when_both_populated(self):
        rows = _rows(("DEU", 2023, 100.0), ("DEU", 2024, 200.0))
        assert latest_non_null(rows, "DEU", "IND") == (2024, 200.0)

    def test_isolates_by_country(self):
        rows = _rows(("DEU", 2024, 1.0), ("IND", 2025, 2.0))
        assert latest_non_null(rows, "DEU", "IND") == (2024, 1.0)

    def test_raises_when_every_year_is_null(self):
        with pytest.raises(MissingValueError):
            latest_non_null(_rows(("DEU", 2025, None)), "DEU", "IND")

    def test_raises_for_unknown_country(self):
        with pytest.raises(MissingValueError):
            latest_non_null(_rows(("DEU", 2024, 1.0)), "FRA", "IND")


class TestAdultShare:
    def test_removes_the_15_to_17_cohort(self):
        # 0-14 = 13.89 -> 15-17 approximated at 2.778 -> adult 18+ = 0.8333
        assert derive_adult_share(13.89) == pytest.approx(0.8333, abs=1e-4)

    def test_naive_derivation_would_overstate(self):
        naive = 1 - 13.89 / 100
        assert derive_adult_share(13.89) < naive
        assert naive - derive_adult_share(13.89) == pytest.approx(0.0278, abs=1e-4)

    def test_observed_band_overrides_the_approximation(self):
        assert derive_adult_share(13.89, age_15_17_pct=3.0) == pytest.approx(0.8311, abs=1e-4)

    def test_rejects_implausible_result(self):
        with pytest.raises(MissingValueError):
            derive_adult_share(60.0)


class TestFixtureTransform:
    def test_transform_resolves_each_indicator_independently(self, fixtures, monkeypatch):
        fetcher = WorldBankFetcher()
        monkeypatch.setattr(
            type(fetcher), "raw_path", property(lambda self: fixtures / "worldbank.json")
        )
        frame = fetcher.transform(fetcher.raw_path)

        years = frame.set_index(["country_code", "indicator"])["year"]
        # Population runs to 2025; health expenditure lags. A single fixed-year join
        # would have discarded one of them.
        assert years[("DEU", "population_total")] >= years[("DEU", "health_exp_pc_usd")]
        assert set(frame["confidence_tier"]) == {"A"}

    def test_countries_carry_tier_b_adult_share(self, fixtures, monkeypatch):
        fetcher = WorldBankFetcher()
        monkeypatch.setattr(
            type(fetcher), "raw_path", property(lambda self: fixtures / "worldbank.json")
        )
        countries = build_countries(fetcher.transform(fetcher.raw_path))
        assert set(countries["adult_share_tier"]) == {"B"}
        assert countries["adult_share"].between(0.5, 0.95).all()

    def test_validate_rejects_incomplete_coverage(self, fixtures):
        # The fixture holds only DEU and IND, not all ten target markets.
        with pytest.raises(CoverageError):
            WorldBankFetcher().validate(fixtures / "worldbank.json")
