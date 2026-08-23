"""Unit tests for biet_engine.sensitivity — M9 section 10 (OWSA half)."""

from __future__ import annotations

import pytest

from biet_engine.constants import ConfidenceTier
from biet_engine.models import SensitivityParam, Substitution, Valued
from biet_engine.sensitivity import default_params, range_for, run_owsa

from ..conftest import (
    make_country_input,
    make_engine_input,
    make_provenance,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _differentiated_country(code: str = "USA", horizon: int = 2):
    """A market where the new therapy costs more than what it displaces, so
    budget impact is non-zero and swings are actually observable."""
    new = make_therapy_input(drug_id=2, is_new=True, unit_price=300.0, currency="USD")
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    return make_country_input(
        country_code=code, currency="USD", horizon=horizon,
        therapies=(comparator,), new_therapy=new,
        baseline_shares={1: (1.0,) * horizon},
        substitution=Substitution(shares={1: make_valued(1.0)}),
    )


def test_published_bounds_take_priority_over_tier_defaults() -> None:
    value = Valued(value=0.60, low=0.55, high=0.65, provenance=make_provenance(tier=ConfidenceTier.C))
    assert range_for(value, is_rate=True) == pytest.approx((0.55, 0.65))


def test_tier_c_range_is_base_plus_minus_two_rse() -> None:
    # Tier C = 30% RSE -> 0.60 x (1 -/+ 0.60) -> [0.24, 0.96].
    value = Valued(value=0.60, provenance=make_provenance(tier=ConfidenceTier.C))
    low, high = range_for(value, is_rate=True)
    assert low == pytest.approx(0.24)
    assert high == pytest.approx(0.96)


def test_rate_range_is_clipped_at_one() -> None:
    # 0.90 x 1.6 = 1.44, outside a rate's domain -> clipped to 1.0, silently.
    value = Valued(value=0.90, provenance=make_provenance(tier=ConfidenceTier.C))
    _, high = range_for(value, is_rate=True)
    assert high == 1.0


def test_non_rate_range_is_floored_at_zero_not_one() -> None:
    value = Valued(value=100.0, provenance=make_provenance(tier=ConfidenceTier.D))
    low, high = range_for(value, is_rate=False)
    assert low == 0.0            # 100 x (1 - 1.0) = 0
    assert high == pytest.approx(200.0)


def test_swing_is_absolute_difference_and_ranking_is_descending() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_owsa(inputs)

    for entry in result.entries:
        assert entry.swing == pytest.approx(abs(entry.result_at_high - entry.result_at_low))

    swings = [e.swing for e in result.entries]
    assert swings == sorted(swings, reverse=True)
    assert [e.rank for e in result.entries] == list(range(1, len(result.entries) + 1))


def test_multiplicative_funnel_gives_equal_swings_for_equal_relative_ranges() -> None:
    """Not a defect: the funnel is a pure product, so a +/-k relative change
    on any one factor moves the product by the same relative amount. With
    every default parameter at the same tier (hence the same relative range),
    identical swings are the mathematically correct answer."""
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_owsa(inputs)
    swings = [e.swing for e in result.entries]
    # Relative comparison, not exact equality: the factors are multiplied in
    # a different order per parameter, so the products agree to ~9 significant
    # figures rather than bit-for-bit.
    assert all(s == pytest.approx(swings[0], rel=1e-9) for s in swings)


def test_zero_swing_parameter_is_retained_in_the_ranking() -> None:
    # Zero uptake -> zero budget impact at every bound -> every swing is 0,
    # and every parameter must still appear (section 6: "a parameter that
    # does not move the answer is a finding").
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.0, 0.0)),
    )
    result = run_owsa(inputs)
    assert len(result.entries) == len(default_params(inputs))
    assert all(e.swing == 0 for e in result.entries)


def test_unknown_parameter_path_warns_rather_than_reporting_a_silent_zero() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    params = (SensitivityParam(
        parameter_path="therapy.999.unit_price", label="Unswept price",
        base_value=1.0, low_value=0.5, high_value=1.5,
    ),)
    result = run_owsa(inputs, params)

    assert result.entries[0].swing == 0
    assert any(w.code == "PARAMETER_NOT_SWEPT" for w in result.warnings)


def test_base_result_matches_the_forward_run() -> None:
    from biet_engine.impact import compute_budget_impact

    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_owsa(inputs)
    expected = compute_budget_impact(inputs).totals.cumulative.amount
    assert result.base_result == pytest.approx(expected)


def test_default_params_omits_adult_share_when_unresolved() -> None:
    country = _differentiated_country().model_copy(update={"adult_share": None})
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    paths = {p.parameter_path for p in default_params(inputs)}
    assert "countries.adult_share" not in paths


def test_substituting_adult_share_leaves_an_unresolved_market_untouched() -> None:
    """`_with_parameter` tested directly: `run_owsa` computes its base case
    first, and `compute_budget_impact` raises on an unresolved `adult_share`
    before any substitution happens — so this branch is only reachable at
    the function itself."""
    from biet_engine.sensitivity import _with_parameter

    resolved = _differentiated_country("USA")
    unresolved = _differentiated_country("DEU").model_copy(update={"adult_share": None})
    inputs = make_engine_input(
        countries=(resolved, unresolved), horizon_years=2, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.05, 0.10)),
    )

    swapped = _with_parameter(inputs, "countries.adult_share", 0.70)

    assert swapped.countries[0].adult_share is not None
    assert swapped.countries[0].adult_share.value == pytest.approx(0.70)
    assert swapped.countries[1].adult_share is None      # left as-is, not fabricated


def test_substituting_an_unknown_path_leaves_every_market_untouched() -> None:
    from biet_engine.sensitivity import _with_parameter

    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    swapped = _with_parameter(inputs, "therapy.999.unit_price", 42.0)
    assert swapped.countries == inputs.countries


def test_default_params_empty_for_no_markets() -> None:
    inputs = make_engine_input(horizon_years=1)
    empty = inputs.model_copy(update={"countries": ()})
    assert default_params(empty) == ()
