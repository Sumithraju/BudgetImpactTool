"""Property tests for biet_engine.landscape — M14 section 10.

Shares summing to 1.0 is the invariant M4 already requires of a baseline mix.
Projection rewrites every share in that mix, so it is the invariant most
likely to be broken by a change here and the one worth testing over random
inputs rather than examples.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from biet_engine.constants import MAX_ENTRANT_TOTAL_SHARE
from biet_engine.landscape import project_landscape
from biet_engine.models import PipelineEntrant

from ..conftest import make_valued

_share = st.floats(min_value=0.01, max_value=0.95, allow_nan=False, allow_infinity=False)


@st.composite
def _baseline(draw: st.DrawFn, horizon: int) -> dict[int, tuple[float, ...]]:
    count = draw(st.integers(min_value=2, max_value=5))
    weights = draw(st.lists(_share, min_size=count, max_size=count))
    total = sum(weights)
    return {
        i + 1: tuple([w / total] * horizon) for i, w in enumerate(weights)
    }


@st.composite
def _entrants(draw: st.DrawFn, horizon: int) -> list[PipelineEntrant]:
    count = draw(st.integers(min_value=0, max_value=3))
    return [
        PipelineEntrant(
            drug_id=100 + i,
            name=f"E{i}",
            entry_year=draw(st.integers(min_value=1, max_value=horizon + 1)),
            terminal_share=make_valued(draw(st.floats(min_value=0.01, max_value=0.9))),
            ramp_years=draw(st.integers(min_value=1, max_value=4)),
        )
        for i in range(count)
    ]


@given(horizon=st.integers(min_value=1, max_value=5), data=st.data())
def test_projected_shares_always_sum_to_one(horizon: int, data: st.DataObject) -> None:
    baseline = data.draw(_baseline(horizon))
    entrants = data.draw(_entrants(horizon))

    result = project_landscape(baseline, entrants, horizon_years=horizon)
    for year in range(horizon):
        total = sum(v[year] for v in result.baseline_shares.values())
        assert total == pytest.approx(1.0, abs=1e-9)


@given(horizon=st.integers(min_value=1, max_value=5), data=st.data())
def test_no_share_is_ever_negative(horizon: int, data: st.DataObject) -> None:
    baseline = data.draw(_baseline(horizon))
    entrants = data.draw(_entrants(horizon))

    result = project_landscape(baseline, entrants, horizon_years=horizon)
    for shares in result.baseline_shares.values():
        assert all(s >= 0.0 for s in shares)


@given(horizon=st.integers(min_value=1, max_value=5), data=st.data())
def test_entrants_never_exceed_the_cap(horizon: int, data: st.DataObject) -> None:
    baseline = data.draw(_baseline(horizon))
    entrants = data.draw(_entrants(horizon))

    result = project_landscape(baseline, entrants, horizon_years=horizon)
    admitted = {e.drug_id for e in result.admitted}
    for year in range(horizon):
        occupied = sum(
            v[year] for k, v in result.baseline_shares.items() if k in admitted
        )
        assert occupied <= MAX_ENTRANT_TOTAL_SHARE + 1e-9


@given(horizon=st.integers(min_value=2, max_value=5), data=st.data())
def test_incumbent_shares_are_non_increasing_in_entrant_presence(
    horizon: int, data: st.DataObject,
) -> None:
    """Admitting entrants can only take share from incumbents, never give it.
    If it could, an entrant would be growing the market rather than competing
    in it."""
    baseline = data.draw(_baseline(horizon))
    entrants = data.draw(_entrants(horizon))

    projected = project_landscape(baseline, entrants, horizon_years=horizon)
    for drug_id, original in baseline.items():
        after = projected.baseline_shares[drug_id]
        for year in range(horizon):
            assert after[year] <= original[year] + 1e-9
