"""NADAC transform rules. No network access."""

from datetime import date

import pytest

from data.ingestion.errors import SourceValidationError
from data.ingestion.sources.nadac import NadacFetcher, candidate_dates


class TestCandidateDates:
    def test_resolves_to_wednesdays_most_recent_first(self):
        # 2026-08-23 is a Sunday; the preceding Wednesday is 2026-08-19.
        dates = candidate_dates(date(2026, 8, 23))
        assert dates[0] == "08-19-2026"
        assert dates[1] == "08-12-2026"

    def test_on_a_wednesday_returns_that_day(self):
        assert candidate_dates(date(2026, 8, 19))[0] == "08-19-2026"

    def test_provides_a_fallback_window(self):
        assert len(candidate_dates(date(2026, 8, 23))) >= 4


class TestTransform:
    def test_keeps_only_target_molecules(self, fixtures):
        frame = NadacFetcher().transform(fixtures / "nadac_sample.csv")
        descriptions = " ".join(frame["ndc_description"]).upper()
        assert "ATORVASTATIN" not in descriptions

    def test_deduplicates_by_ndc_keeping_latest_effective_date(self, fixtures):
        frame = NadacFetcher().transform(fixtures / "nadac_sample.csv")
        glargine = frame[frame["ndc"] == 955172901]
        assert len(glargine) == 1
        assert glargine["nadac_per_unit"].iloc[0] == pytest.approx(10.91483)

    def test_no_branded_incretin_pricing_is_available(self, fixtures):
        # Documents the established constraint: NADAC covers multi-source products,
        # so branded semaglutide and tirzepatide are absent and must come from the
        # curated seed table instead.
        frame = NadacFetcher().transform(fixtures / "nadac_sample.csv")
        descriptions = " ".join(frame["ndc_description"]).upper()
        assert "SEMAGLUTIDE" not in descriptions
        assert "TIRZEPATIDE" not in descriptions

    def test_validate_rejects_missing_columns(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("Foo,Bar\n1,2\n")
        with pytest.raises(SourceValidationError):
            NadacFetcher().validate(path)
