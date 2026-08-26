"""Unit tests for biet_engine.persistence — M6 section 10."""

from __future__ import annotations

import math

import pytest

from biet_engine.persistence import persistence_fraction

# M6 section 5.2 reference table. Assert every row to 4 decimal places.
REFERENCE_VALUES = [
    (1.00, 1.0000),
    (0.85, 0.9230),
    (0.70, 0.8411),
    (0.50, 0.7213),
    (0.30, 0.5814),
    (0.20, 0.4971),
    (0.05, 0.3171),
]


@pytest.mark.parametrize("p12, expected", REFERENCE_VALUES)
def test_persistence_fraction_reference_values(p12: float, expected: float) -> None:
    assert persistence_fraction(p12) == pytest.approx(expected, abs=1e-4)


def test_persistence_fraction_full_persistence_returns_exactly_one() -> None:
    assert persistence_fraction(1.0) == 1.0


def test_persistence_fraction_zero_raises_value_error() -> None:
    with pytest.raises(ValueError, match="p12"):
        persistence_fraction(0.0)


def test_persistence_fraction_above_one_raises_value_error() -> None:
    with pytest.raises(ValueError, match="p12"):
        persistence_fraction(1.5)


def test_persistence_fraction_negative_raises_value_error() -> None:
    with pytest.raises(ValueError, match="p12"):
        persistence_fraction(-0.1)


def test_persistence_fraction_nan_raises_value_error() -> None:
    with pytest.raises(ValueError, match="p12"):
        persistence_fraction(math.nan)


def test_persistence_fraction_near_one_uses_log1p_path_and_stays_accurate() -> None:
    p12 = 0.9999
    # Closed form evaluated independently via math.log (not log1p), as an
    # analytic cross-check that the log1p branch agrees with the direct one.
    analytic = (1 - p12) / (-math.log(p12))
    assert persistence_fraction(p12) == pytest.approx(analytic, abs=1e-9)
