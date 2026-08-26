"""WHO GHO filter rules. No network access."""

import json

import pytest

from data.ingestion.constants import WHO_AGE_GROUP_ADULT, WHO_SEX_BOTH
from data.ingestion.sources.who_gho import WhoGhoFetcher, apply_who_filters


def _row(**kw):
    base = {
        "SpatialDimType": "COUNTRY", "SpatialDim": "DEU",
        "Dim1": WHO_SEX_BOTH, "Dim2": WHO_AGE_GROUP_ADULT,
        "TimeDim": 2024, "NumericValue": 20.64, "Low": 17.59, "High": 23.91,
    }
    return base | kw


class TestFilters:
    def test_excludes_world_bank_income_group_aggregates(self):
        rows = [_row(), _row(SpatialDimType="WORLDBANKINCOMEGROUP", SpatialDim="WB_UMI")]
        assert len(apply_who_filters(rows)) == 1

    def test_excludes_region_aggregates(self):
        rows = [_row(), _row(SpatialDimType="REGION", SpatialDim="EUR")]
        assert len(apply_who_filters(rows)) == 1

    def test_excludes_single_sex_series(self):
        rows = [_row(), _row(Dim1="SEX_MLE"), _row(Dim1="SEX_FMLE")]
        assert len(apply_who_filters(rows)) == 1

    def test_excludes_non_adult_age_groups(self):
        rows = [_row(), _row(Dim2="AGEGROUP_YEARS10-19")]
        assert len(apply_who_filters(rows)) == 1

    def test_excludes_countries_outside_the_target_set(self):
        rows = [_row(), _row(SpatialDim="FSM")]
        assert len(apply_who_filters(rows)) == 1

    def test_all_four_filters_applied_together(self):
        rows = [
            _row(),
            _row(SpatialDimType="REGION"),
            _row(Dim1="SEX_MLE"),
            _row(Dim2="AGEGROUP_YEARS10-19"),
            _row(SpatialDim="FSM"),
        ]
        assert len(apply_who_filters(rows)) == 1


class TestTransform:
    def test_keeps_published_confidence_bounds(self, fixtures, monkeypatch):
        fetcher = WhoGhoFetcher()
        monkeypatch.setattr(
            type(fetcher), "raw_path", property(lambda self: fixtures / "who_gho.json")
        )
        frame = fetcher.transform(fetcher.raw_path)

        # M9 parameterises PSA directly from these; losing them is a defect.
        assert frame["prevalence_low"].notna().all()
        assert frame["prevalence_high"].notna().all()
        assert (frame["prevalence_low"] <= frame["prevalence_pct"]).all()
        assert (frame["prevalence_pct"] <= frame["prevalence_high"]).all()

    def test_diabetes_series_is_stale(self, fixtures, monkeypatch):
        fetcher = WhoGhoFetcher()
        monkeypatch.setattr(
            type(fetcher), "raw_path", property(lambda self: fixtures / "who_gho.json")
        )
        frame = fetcher.transform(fetcher.raw_path)
        diabetes = frame[frame["indicator"] == "diabetes_prevalence"]
        # NCD_GLUC_04 has not been refreshed since 2014.
        assert diabetes["year"].max() == 2014

    def test_obesity_series_is_current(self, fixtures, monkeypatch):
        fetcher = WhoGhoFetcher()
        monkeypatch.setattr(
            type(fetcher), "raw_path", property(lambda self: fixtures / "who_gho.json")
        )
        frame = fetcher.transform(fetcher.raw_path)
        assert frame[frame["indicator"] == "obesity_prevalence"]["year"].max() == 2024
