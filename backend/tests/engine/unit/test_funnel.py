"""Unit tests for biet_engine.funnel — M2 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import FunnelStage
from biet_engine.exceptions import FunnelInvariantError, UnresolvedParameterError
from biet_engine.funnel import compute_funnel
from biet_engine.models import Valued

from ..conftest import make_country_input, make_valued

# Germany, obesity, Year 1 — M2 section 10 golden case.
GOLDEN_EXPECTED = {
    FunnelStage.TOTAL_POPULATION: 83_500_000,
    FunnelStage.ADULT_POPULATION: 68_470_000,
    FunnelStage.DISEASED: 14_132_208,
    FunnelStage.DIAGNOSED: 8_479_325,
    FunnelStage.TREATED: 1_271_899,
    FunnelStage.LABEL_ELIGIBLE: 445_165,
    FunnelStage.ADDRESSABLE: 311_615,
}


def _criteria_factor(value: float = 0.350) -> Valued:
    return make_valued(value)


def test_golden_case_reproduces_within_one_unit() -> None:
    country = make_country_input()
    result = compute_funnel(country, _criteria_factor(), year=1)

    by_stage = {s.stage: s.value for s in result.stages}
    for stage, expected in GOLDEN_EXPECTED.items():
        assert by_stage[stage] == pytest.approx(expected, abs=1.0), stage

    assert result.addressable == pytest.approx(311_615, abs=1.0)


def test_year_1_applies_growth_exponent_zero() -> None:
    country = make_country_input(population_total=1_000_000, population_growth=0.02)
    result = compute_funnel(country, _criteria_factor(), year=1)
    total = result.stages[0].value
    assert total == pytest.approx(1_000_000)


def test_year_2_applies_growth_exponent_one() -> None:
    country = make_country_input(population_total=1_000_000, population_growth=0.02)
    result = compute_funnel(country, _criteria_factor(), year=2)
    total = result.stages[0].value
    assert total == pytest.approx(1_000_000 * 1.02)


def test_negative_population_growth_reduces_population() -> None:
    country = make_country_input(population_total=1_000_000, population_growth=-0.01)
    result = compute_funnel(country, _criteria_factor(), year=2)
    assert result.stages[0].value < 1_000_000


def test_omitting_adult_share_raises_and_does_not_default_to_one() -> None:
    country = make_country_input(adult_share=None)
    with pytest.raises(UnresolvedParameterError, match="adult_share"):
        compute_funnel(country, _criteria_factor(), year=1)


def test_factor_greater_than_one_raises_funnel_invariant_error() -> None:
    country = make_country_input()
    with pytest.raises(FunnelInvariantError):
        compute_funnel(country, _criteria_factor(value=1.2), year=1)


def test_negative_criteria_factor_raises_value_error() -> None:
    country = make_country_input()
    with pytest.raises(ValueError, match="criteria_factor"):
        compute_funnel(country, _criteria_factor(value=-0.1), year=1)


def test_prevalence_entered_as_percent_raises_value_error() -> None:
    country = make_country_input(prevalence=20.64)          # should be 0.2064
    with pytest.raises(ValueError, match="prevalence"):
        compute_funnel(country, _criteria_factor(), year=1)


def test_year_below_one_raises_value_error() -> None:
    country = make_country_input()
    with pytest.raises(ValueError, match="year"):
        compute_funnel(country, _criteria_factor(), year=0)


def test_every_stage_carries_provenance() -> None:
    country = make_country_input()
    result = compute_funnel(country, _criteria_factor(), year=1)

    assert all(stage.provenance is not None for stage in result.stages)
    assert result.stages[0].factor is None
    assert all(stage.factor is not None for stage in result.stages[1:])
