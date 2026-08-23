"""Property tests for biet_engine.cost — M5 section 10, "Property" class."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from biet_engine.cost import compute_therapy_cost

from ..conftest import make_therapy_input

_PRICE = st.floats(min_value=0.01, max_value=1e6, allow_nan=False)
_OFFSET = st.floats(min_value=0.0, max_value=1e6, allow_nan=False)


@given(price_a=_PRICE, price_b=_PRICE)
def test_acquisition_cost_monotonically_increasing_in_price(
    price_a: float, price_b: float,
) -> None:
    lower, higher = sorted((price_a, price_b))
    cost_lower = compute_therapy_cost(
        make_therapy_input(unit_price=lower), country_code="USA"
    )
    cost_higher = compute_therapy_cost(
        make_therapy_input(unit_price=higher), country_code="USA"
    )
    assert cost_higher.acquisition.amount >= cost_lower.acquisition.amount


@given(offset_a=_OFFSET, offset_b=_OFFSET)
def test_total_cost_monotonically_decreasing_in_offset(
    offset_a: float, offset_b: float,
) -> None:
    lower, higher = sorted((offset_a, offset_b))
    cost_lower_offset = compute_therapy_cost(
        make_therapy_input(offset=lower), country_code="USA"
    )
    cost_higher_offset = compute_therapy_cost(
        make_therapy_input(offset=higher), country_code="USA"
    )
    assert cost_higher_offset.total.amount <= cost_lower_offset.total.amount
