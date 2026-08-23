"""Unit tests for biet_engine.distributions — M9 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import ConfidenceTier
from biet_engine.distributions import (
    beta_from_moments,
    gamma_from_moments,
    sd_from_interval,
    sd_from_tier,
    triangular_from_range,
)


def test_beta_method_of_moments_reference_case() -> None:
    params = beta_from_moments(mean=0.5, sd=0.1)
    assert params.alpha == pytest.approx(12.0)
    assert params.beta == pytest.approx(12.0)
    assert not params.shrunk


def test_beta_shrinks_when_variance_exceeds_ceiling() -> None:
    # m(1-m) = 0.09 at m=0.1, so an SD of 0.5 (v=0.25) is far over the ceiling.
    params = beta_from_moments(mean=0.1, sd=0.5)
    assert params.shrunk
    assert params.alpha > 0 and params.beta > 0


def test_beta_rejects_degenerate_mean() -> None:
    with pytest.raises(ValueError, match="Beta mean"):
        beta_from_moments(mean=0.0, sd=0.1)
    with pytest.raises(ValueError, match="Beta mean"):
        beta_from_moments(mean=1.0, sd=0.1)


def test_gamma_method_of_moments_reference_case() -> None:
    params = gamma_from_moments(mean=100.0, sd=20.0)
    assert params.shape == pytest.approx(25.0)
    assert params.scale == pytest.approx(4.0)


def test_gamma_rejects_non_positive_inputs() -> None:
    with pytest.raises(ValueError, match="Gamma mean"):
        gamma_from_moments(mean=0.0, sd=1.0)
    with pytest.raises(ValueError, match="Gamma sd"):
        gamma_from_moments(mean=1.0, sd=0.0)


def test_sd_from_published_interval_deu_obesity() -> None:
    # DEU obesity published bounds [0.1759, 0.2391] -> SD 0.016122.
    assert sd_from_interval(0.1759, 0.2391) == pytest.approx(0.016122, abs=1e-6)


def test_sd_from_tier_scales_with_the_mean() -> None:
    # Tier C is a 30% relative standard error.
    assert sd_from_tier(0.60, ConfidenceTier.C) == pytest.approx(0.18)
    assert sd_from_tier(0.60, ConfidenceTier.B) == pytest.approx(0.09)


def test_triangular_from_range() -> None:
    params = triangular_from_range(mode=100.0, relative_range=0.2)
    assert params.low == pytest.approx(80.0)
    assert params.mode == pytest.approx(100.0)
    assert params.high == pytest.approx(120.0)


def test_triangular_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="mode"):
        triangular_from_range(mode=0.0, relative_range=0.2)
    with pytest.raises(ValueError, match="relative_range"):
        triangular_from_range(mode=100.0, relative_range=1.5)
