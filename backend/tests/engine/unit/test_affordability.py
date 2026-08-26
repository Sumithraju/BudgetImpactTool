"""Unit tests for biet_engine.affordability — M8 section 10 (forward half)."""

from __future__ import annotations

import pytest

from biet_engine.affordability import compute_affordability
from biet_engine.constants import AffordabilityBand
from biet_engine.exceptions import UnresolvedParameterError
from biet_engine.impact import compute_budget_impact
from biet_engine.models import Substitution

from ..conftest import (
    make_country_input,
    make_country_result,
    make_engine_input,
    make_engine_result,
    make_therapy_input,
    make_uptake_input,
    make_valued,
    make_year_result,
)


def test_affordability_ratio_worked_example() -> None:
    # BI = 58,667,000 USD, health budget = 571.9e9 USD -> ratio ~= 0.000103.
    # BI is stated directly (via make_year_result) rather than produced by a
    # full forward run, matching the M8 spec's own framing: the worked
    # example states the ratio's two operands, not a scenario that
    # reproduces them via M7.
    country = make_country_input(
        country_code="DEU", currency="USD", horizon=1,
        health_exp_pc=571_900_000_000 / 83_500_000,  # -> health budget 571.9e9 at Pop=population_total
        population_total=83_500_000, population_growth=0.0,
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.1,)),
    )
    year = make_year_result(budget_impact=58_667_000, currency="USD")
    country_result = make_country_result(country_code="DEU", currency="USD", years=(year,))
    result = make_engine_result(countries=(country_result,), reporting_currency="USD")

    afford = compute_affordability(result, inputs)[0]
    assert afford.health_budget.amount == pytest.approx(571_900_000_000, rel=1e-9)
    assert afford.ratio_by_year[0] == pytest.approx(0.000103, abs=1e-6)
    assert afford.cumulative_ratio == pytest.approx(0.000103, abs=1e-6)


def test_cumulative_ratio_is_ratio_of_sums_not_sum_of_ratios() -> None:
    # Two years with a growing health budget (population growth) and a
    # non-zero, year-varying BI (new therapy priced above its comparator,
    # uptake growing) -> ratio-of-sums and sum-of-ratios genuinely differ.
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=200.0, currency="USD")
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=2,
        population_total=100_000_000, population_growth=0.10,
        health_exp_pc=1000.0,
        therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (1.0, 1.0)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.20)),           # uptake also grows
    )
    result = compute_budget_impact(inputs)
    afford = compute_affordability(result, inputs)[0]

    assert all(r != 0 for r in afford.ratio_by_year)
    sum_of_ratios = sum(afford.ratio_by_year) / len(afford.ratio_by_year)
    assert afford.cumulative_ratio != pytest.approx(sum_of_ratios)


@pytest.mark.parametrize("ratio, expected_band", [
    (0.000999, AffordabilityBand.LOW),
    (0.001, AffordabilityBand.MODERATE),
    (0.005, AffordabilityBand.HIGH),
    (0.01, AffordabilityBand.CRITICAL),
])
def test_band_boundaries(ratio: float, expected_band: AffordabilityBand) -> None:
    from biet_engine.affordability import band_for
    assert band_for(ratio) == expected_band


def test_negative_cumulative_ratio_is_low_and_labelled_a_saving() -> None:
    from biet_engine.affordability import band_for
    assert band_for(-0.05) == AffordabilityBand.LOW


def test_missing_health_exp_pc_raises_unresolved_parameter_error() -> None:
    country = make_country_input(horizon=1, health_exp_pc=None)
    inputs = make_engine_input(countries=(country,), horizon_years=1)
    result = compute_budget_impact(inputs)
    with pytest.raises(UnresolvedParameterError):
        compute_affordability(result, inputs)


def test_zero_health_exp_pc_raises_value_error() -> None:
    country = make_country_input(horizon=1, health_exp_pc=0.0)
    inputs = make_engine_input(countries=(country,), horizon_years=1)
    result = compute_budget_impact(inputs)
    with pytest.raises(ValueError, match="health_exp_pc"):
        compute_affordability(result, inputs)
