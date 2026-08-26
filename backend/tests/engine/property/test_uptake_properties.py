"""Property tests for biet_engine.uptake — M4 section 10, "Property" class."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from biet_engine.constants import UptakeCurve
from biet_engine.models import Substitution, UptakeInput
from biet_engine.uptake import build_market_mix, project_uptake

from ..conftest import make_valued

_SHARE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@given(
    year_1=_SHARE, terminal=_SHARE, horizon=st.integers(min_value=1, max_value=5),
)
def test_linear_uptake_non_decreasing_when_terminal_ge_year_1(
    year_1: float, terminal: float, horizon: int,
) -> None:
    if terminal < year_1:
        return  # not the monotonic case this property targets
    inputs = UptakeInput(
        curve=UptakeCurve.LINEAR, year_1=make_valued(year_1), terminal=make_valued(terminal),
    )
    result = project_uptake(inputs, horizon)
    assert all(result[i] <= result[i + 1] + 1e-12 for i in range(len(result) - 1))


@given(
    m1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    m2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    u=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    sigma1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_share_accounting_invariant_holds(m1: float, m2: float, u: float, sigma1: float) -> None:
    total = m1 + m2
    if total <= 0:
        return
    m1, m2 = m1 / total, m2 / total          # normalise baseline to sum to 1.0
    baseline = {1: [m1], 2: [m2]}
    substitution = Substitution(
        shares={1: make_valued(sigma1), 2: make_valued(1 - sigma1)}
    )
    mix = build_market_mix(baseline, uptake=[u], substitution=substitution,
                            country_code="DEU")[0]
    assert math.isclose(mix.uptake + sum(mix.shares_with.values()), 1.0, abs_tol=1e-9)


@given(
    m1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    m2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    u=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    sigma1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_every_share_with_in_unit_interval(m1: float, m2: float, u: float, sigma1: float) -> None:
    total = m1 + m2
    if total <= 0:
        return
    m1, m2 = m1 / total, m2 / total
    baseline = {1: [m1], 2: [m2]}
    substitution = Substitution(
        shares={1: make_valued(sigma1), 2: make_valued(1 - sigma1)}
    )
    mix = build_market_mix(baseline, uptake=[u], substitution=substitution,
                            country_code="DEU")[0]
    assert all(0 - 1e-9 <= share <= 1 + 1e-9 for share in mix.shares_with.values())
