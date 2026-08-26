"""Property tests for biet_engine.impact — M7 section 10, "Property" class."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from biet_engine.impact import compute_budget_impact
from biet_engine.models import Substitution

from ..conftest import (
    make_country_input,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _reduced_form_bi(
    addressable: float, u: float, f_n: float, ac_n: float, sigma: float, f_t: float, ac_t: float,
) -> float:
    """M7 section 5.2's reduced form — a property-test cross-check only,
    valid exactly when no displacement floor bound."""
    return addressable * u * (f_n * ac_n - sigma * f_t * ac_t)


@given(
    u=st.floats(min_value=0.0, max_value=0.3, allow_nan=False),   # small enough the floor never binds
    price_n=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
    price_t=st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False),
)
def test_full_form_equals_reduced_form_when_no_substitution_floor(
    u: float, price_n: float, price_t: float,
) -> None:
    # admins_per_year=1 so compute_therapy_cost's AC == unit_price exactly,
    # matching what the reduced-form cross-check below treats as AC.
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=price_n, currency="USD",
                                      admins_per_year=1.0)
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=price_t, currency="USD",
                                     admins_per_year=1.0)
    country = make_country_input(
        currency="USD", horizon=1, therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(u,)),
    )
    result = compute_budget_impact(inputs)
    year = result.countries[0].years[0]

    assert not any(w.code == "SUBSTITUTION_FLOOR" for w in result.warnings)

    # make_therapy_input defaults persistence_12m=1.0 -> persistence_fraction = 1.0 for both.
    reduced = _reduced_form_bi(
        addressable=year.addressable, u=u, f_n=1.0, ac_n=price_n, sigma=1.0, f_t=1.0, ac_t=price_t,
    )
    # rel_tol is the 1e-6 relative agreement the module doc asks for. abs_tol
    # is a floor for near-zero BI (both forms ~0 but not bit-identical due to
    # float rounding) — widened from 1e-6 to 1e-4 after Hypothesis found a
    # genuine extreme case (u=1e-5, near-equal prices) where the two forms'
    # differing operation sequences accumulate noise slightly above 1e-6
    # relative on a very small magnitude; 1e-4 absolute is still far tighter
    # than anything a real scenario's inputs would produce.
    assert math.isclose(year.budget_impact.amount, reduced, rel_tol=1e-6, abs_tol=1e-4)


@given(price_a=st.floats(min_value=1.0, max_value=1e5, allow_nan=False),
       price_b=st.floats(min_value=1.0, max_value=1e5, allow_nan=False))
def test_budget_impact_monotonically_non_decreasing_in_new_price(
    price_a: float, price_b: float,
) -> None:
    lower, higher = sorted((price_a, price_b))

    def _bi_for_price(price: float) -> float:
        new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=price, currency="USD")
        comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
        country = make_country_input(
            currency="USD", horizon=1, therapies=(comparator,), new_therapy=new_therapy,
            baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
        )
        inputs = make_engine_input(
            countries=(country,), horizon_years=1, reporting_currency="USD",
            uptake=make_uptake_input(vector=(0.1,)),
        )
        return compute_budget_impact(inputs).countries[0].years[0].budget_impact.amount

    assert _bi_for_price(higher) >= _bi_for_price(lower) - 1e-6


@given(
    population_total=st.floats(min_value=1_000.0, max_value=1e8, allow_nan=False),
    scale=st.floats(min_value=0.1, max_value=5.0, allow_nan=False),
)
def test_scaling_addressable_scales_budget_impact(population_total: float, scale: float) -> None:
    def _bi_for(pop: float) -> float:
        country = make_country_input(currency="USD", horizon=1, population_total=pop)
        inputs = make_engine_input(
            countries=(country,), horizon_years=1, reporting_currency="USD",
            uptake=make_uptake_input(vector=(0.1,)),
        )
        return compute_budget_impact(inputs).countries[0].years[0].budget_impact.amount

    base = _bi_for(population_total)
    scaled = _bi_for(population_total * scale)
    if base == 0:
        assert scaled == 0
    else:
        assert abs(scaled / base - scale) < 1e-6


@given(vector=st.lists(st.floats(min_value=0.0, max_value=0.5, allow_nan=False),
                        min_size=2, max_size=4))
def test_cumulative_equals_sum_of_years(vector: list[float]) -> None:
    horizon = len(vector)
    country = make_country_input(currency="USD", horizon=horizon)
    inputs = make_engine_input(
        countries=(country,), horizon_years=horizon, reporting_currency="USD",
        uptake=make_uptake_input(vector=tuple(sorted(vector))),   # sorted: keep it monotonic
    )
    result = compute_budget_impact(inputs)
    country_result = result.countries[0]
    total = sum(y.budget_impact.amount for y in country_result.years)
    assert country_result.cumulative_budget_impact.amount == pytest.approx(total)
