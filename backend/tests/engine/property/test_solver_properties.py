"""Property tests for biet_engine.solver — M8 section 10, "Property" class."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from biet_engine.solver import solve_price

from ..conftest import make_country_input, make_engine_input, make_uptake_input


@given(target_a=st.floats(min_value=1e-4, max_value=0.5, allow_nan=False),
       target_b=st.floats(min_value=1e-4, max_value=0.5, allow_nan=False))
def test_p_star_monotonically_increasing_in_target_ratio(target_a: float, target_b: float) -> None:
    lower, higher = sorted((target_a, target_b))
    country = make_country_input(country_code="USA", currency="USD", horizon=1)
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05,)),
    )
    price_lower = solve_price(inputs, target_ratio=lower).entries[0].max_unit_price_usd
    price_higher = solve_price(inputs, target_ratio=higher).entries[0].max_unit_price_usd

    assert price_lower is not None and price_higher is not None
    assert price_higher >= price_lower - 1e-6


@given(uptake_a=st.floats(min_value=0.01, max_value=0.5, allow_nan=False),
       uptake_b=st.floats(min_value=0.01, max_value=0.5, allow_nan=False))
def test_p_star_monotonically_decreasing_in_uptake(uptake_a: float, uptake_b: float) -> None:
    lower, higher = sorted((uptake_a, uptake_b))

    def _price_at(u: float) -> float | None:
        country = make_country_input(country_code="USA", currency="USD", horizon=1)
        inputs = make_engine_input(
            countries=(country,), horizon_years=1, reporting_currency="USD",
            uptake=make_uptake_input(vector=(u,)),
        )
        return solve_price(inputs, target_ratio=0.005).entries[0].max_unit_price_usd

    price_lower_uptake = _price_at(lower)
    price_higher_uptake = _price_at(higher)

    # Higher uptake means more patients absorb the same affordability budget
    # -> a lower per-unit price is what stays affordable.
    assert price_lower_uptake is not None and price_higher_uptake is not None
    assert price_higher_uptake <= price_lower_uptake + 1e-6
