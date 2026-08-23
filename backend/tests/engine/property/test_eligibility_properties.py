"""Property tests for biet_engine.eligibility — M3 section 10, "Property" class."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from biet_engine.eligibility import combine_criteria

from ..conftest import make_criterion

_FACTOR = st.floats(min_value=0.001, max_value=1.0, allow_nan=False)


@given(factors=st.lists(_FACTOR, min_size=0, max_size=8))
def test_combined_factor_in_unit_interval(factors: list[float]) -> None:
    criteria = [make_criterion(f"c{i}", f) for i, f in enumerate(factors)]
    result = combine_criteria(criteria)
    assert 0 < result.combined_factor.value <= 1


@given(factors=st.lists(_FACTOR, min_size=1, max_size=6, unique=True))
def test_combination_is_order_independent(factors: list[float]) -> None:
    criteria = [make_criterion(f"c{i}", f) for i, f in enumerate(factors)]
    forward = combine_criteria(criteria).combined_factor.value
    backward = combine_criteria(list(reversed(criteria))).combined_factor.value
    assert math.isclose(forward, backward, rel_tol=1e-9)
