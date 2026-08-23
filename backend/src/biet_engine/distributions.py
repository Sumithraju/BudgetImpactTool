"""Distribution parameterisation for PSA — module M9 section 5.2.

Turns a published interval or a confidence-tier default into the parameters
of the distribution family appropriate to each parameter class. Pure
arithmetic on scalars; the sampling itself is `psa.py`'s job.

Deriving prevalence distributions from WHO's own published bounds rather
than from assumed variation is what makes the uncertainty statement
empirically grounded — that's why M0 insists on carrying `low`/`high`
through the whole pipeline.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from .constants import CI_TO_SD_DIVISOR, TIER_RELATIVE_STANDARD_ERROR, ConfidenceTier


class BetaParams(NamedTuple):
    alpha: float
    beta: float
    shrunk: bool = False                     # True when the SD had to be reduced


class GammaParams(NamedTuple):
    shape: float
    scale: float


class TriangularParams(NamedTuple):
    low: float
    mode: float
    high: float


def sd_from_interval(low: float, high: float) -> float:
    """`(high - low) / 3.92` — the normal approximation to a 95% interval."""
    return (high - low) / CI_TO_SD_DIVISOR


def sd_from_tier(mean: float, tier: ConfidenceTier) -> float:
    """Tier-derived SD where no published interval exists.

    The tier relative standard errors (A published / B 15% / C 30% / D 50%)
    are conventions, not empirical estimates — section 12 says so explicitly,
    which is why they live in `constants` and can be re-based.
    """
    return abs(mean) * TIER_RELATIVE_STANDARD_ERROR[tier]


def beta_from_moments(mean: float, sd: float) -> BetaParams:
    """Beta by method of moments (section 5.2).

        common = m(1-m)/v - 1
        alpha  = m * common
        beta   = (1-m) * common

    Valid only while `v < m(1-m)`. A tier-derived SD can easily violate that
    for a mean near 0 or 1; rather than raising, the SD is shrunk to
    `0.99 * sqrt(m(1-m))` and `shrunk=True` is returned so the caller can
    emit `DISTRIBUTION_SHRUNK`. An over-wide assumed SD is a
    parameterisation artefact, not a modelling failure.

    Raises:
        ValueError: `mean` is outside (0, 1) — degenerate, and the caller
            should hold the point value instead (section 6).
    """
    if not (0 < mean < 1):
        raise ValueError(f"Beta mean must be in (0, 1) exclusive, got {mean!r}")

    max_variance = mean * (1 - mean)
    variance = sd**2
    shrunk = False
    if variance >= max_variance:
        sd = 0.99 * math.sqrt(max_variance)
        variance = sd**2
        shrunk = True

    common = max_variance / variance - 1
    return BetaParams(alpha=mean * common, beta=(1 - mean) * common, shrunk=shrunk)


def gamma_from_moments(mean: float, sd: float) -> GammaParams:
    """`shape = m^2/v`, `scale = v/m` (section 5.2).

    Raises:
        ValueError: `mean <= 0` or `sd <= 0` — Gamma is defined on the
            positive reals, so a non-positive mean has no valid shape.
    """
    if mean <= 0:
        raise ValueError(f"Gamma mean must be positive, got {mean!r}")
    if sd <= 0:
        raise ValueError(f"Gamma sd must be positive, got {sd!r}")
    variance = sd**2
    return GammaParams(shape=mean**2 / variance, scale=variance / mean)


def triangular_from_range(mode: float, relative_range: float) -> TriangularParams:
    """`min = mode x (1 - range)`, `max = mode x (1 + range)` (section 5.2)."""
    if mode <= 0:
        raise ValueError(f"Triangular mode must be positive, got {mode!r}")
    if not (0 < relative_range < 1):
        raise ValueError(f"relative_range must be in (0, 1), got {relative_range!r}")
    return TriangularParams(
        low=mode * (1 - relative_range), mode=mode, high=mode * (1 + relative_range),
    )
