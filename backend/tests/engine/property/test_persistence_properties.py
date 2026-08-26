"""Property tests for biet_engine.persistence — M6 section 10, "Property" class."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from biet_engine.persistence import persistence_fraction

# Excludes exactly 0 and 1: 0 is rejected (undefined), 1 is the exact-branch
# case already covered by its own unit test, not a property over the interval.
_P12 = st.floats(
    min_value=0.0, max_value=1.0, exclude_min=True, exclude_max=True,
    allow_nan=False, allow_infinity=False,
)


@given(p12=_P12)
def test_persistence_fraction_in_unit_interval(p12: float) -> None:
    f = persistence_fraction(p12)
    assert 0 < f <= 1


@given(p12=_P12)
def test_persistence_fraction_at_least_p12(p12: float) -> None:
    """The mean of a strictly decreasing survival function over [0, 12]
    exceeds its endpoint value S(12) = p12."""
    assert persistence_fraction(p12) >= p12


@given(p12=st.floats(min_value=0.01, max_value=0.99, allow_nan=False))
def test_persistence_fraction_strictly_increasing(p12: float) -> None:
    delta = 0.001
    lower = persistence_fraction(max(p12 - delta, 1e-9))
    higher = persistence_fraction(min(p12 + delta, 1.0))
    assert higher > lower


def test_persistence_fraction_approaches_one_as_p12_approaches_one() -> None:
    close_values = [0.9, 0.99, 0.999, 0.9999, 0.99999]
    fractions = [persistence_fraction(p) for p in close_values]
    # Monotonically closing in on 1.0 as p12 climbs toward it.
    assert fractions == sorted(fractions)
    assert fractions[-1] > 0.9999
