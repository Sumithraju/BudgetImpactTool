"""Property tests for biet_engine.outcomes — M16 section 10."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from biet_engine.constants import EventClass
from biet_engine.models import Money, TreatmentEffect
from biet_engine.outcomes import effect_retained, project_outcomes

from ..conftest import make_valued


def _effect(baseline: float, reduction: float, cost: float) -> TreatmentEffect:
    return TreatmentEffect(
        drug_id=1, event=EventClass.MACE, baseline_rate=make_valued(baseline),
        relative_reduction=make_valued(reduction),
        unit_cost=Money(amount=cost, currency="USD"), trial="test",
    )


def _run(patients, baseline, reduction, cost, persistence):
    return project_outcomes(
        patients, [_effect(baseline, reduction, cost)], None,
        persistence=persistence, country_code="USA", currency="USD",
    )


_patients = st.lists(
    st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    min_size=1, max_size=5,
)


@given(
    patients=_patients,
    baseline=st.floats(min_value=0.0, max_value=1.0),
    reduction=st.floats(min_value=0.0, max_value=0.99),
    cost=st.floats(min_value=0.0, max_value=1e6),
    persistence=st.floats(min_value=0.0, max_value=1.0),
)
def test_avoided_events_are_never_negative(
    patients: list[float], baseline: float, reduction: float,
    cost: float, persistence: float,
) -> None:
    """A negative avoided event would be a therapy causing the thing it was
    credited with preventing."""
    result = _run(patients, baseline, reduction, cost, persistence)
    for entry in result.avoided:
        assert entry.avoided >= 0.0
        assert entry.cost_avoided.amount >= 0.0


@given(
    patients=_patients,
    baseline=st.floats(min_value=0.0, max_value=1.0),
    reduction=st.floats(min_value=0.0, max_value=0.99),
    cost=st.floats(min_value=0.0, max_value=1e6),
    persistence=st.floats(min_value=0.0, max_value=1.0),
)
def test_avoided_never_exceeds_the_events_that_would_have_happened(
    patients: list[float], baseline: float, reduction: float,
    cost: float, persistence: float,
) -> None:
    """You cannot avoid more events than the baseline produced."""
    result = _run(patients, baseline, reduction, cost, persistence)
    for entry in result.avoided:
        assert entry.avoided <= entry.events_without + 1e-9
        assert entry.events_with >= -1e-9


@given(
    baseline=st.floats(min_value=0.001, max_value=1.0),
    low=st.floats(min_value=0.0, max_value=0.9),
    extra=st.floats(min_value=0.0, max_value=0.09),
)
def test_more_reduction_never_avoids_fewer_events(
    baseline: float, low: float, extra: float,
) -> None:
    """Monotonicity. A stronger effect that avoided less would invert the
    whole argument the module exists to make."""
    weak = _run([10_000.0], baseline, low, 1_000.0, 1.0)
    strong = _run([10_000.0], baseline, min(low + extra, 0.99), 1_000.0, 1.0)
    assert strong.avoided[0].avoided >= weak.avoided[0].avoided - 1e-9


@given(
    year=st.integers(min_value=1, max_value=10),
    regain=st.floats(min_value=0.0, max_value=1.0),
)
def test_retained_effect_stays_a_fraction(year: int, regain: float) -> None:
    retained = effect_retained(year, regain)
    assert 0.0 <= retained <= 1.0


@given(regain=st.floats(min_value=0.001, max_value=0.999))
def test_retained_effect_never_increases_with_time(regain: float) -> None:
    values = [effect_retained(y, regain) for y in range(1, 6)]
    assert values == sorted(values, reverse=True)
    assert values[0] == pytest.approx(1.0)
