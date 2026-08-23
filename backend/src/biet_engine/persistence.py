"""Persistence & Adherence — ARCHITECTURE.md section 5.4, module M6.

Converts patient headcount into persistence-adjusted treatment-year
equivalents. A patient who discontinues at month five consumes five months of
drug, not twelve. No dependencies; consumed by M7 and M8.
"""

from __future__ import annotations

import math

#: Above this p12, `-ln(p12)` loses precision to float cancellation;
#: `math.log1p` stays accurate all the way to p12 = 1.
_LOG1P_THRESHOLD = 0.999


def persistence_fraction(p12: float) -> float:
    """Mean of the survival function over the first treatment year.

    Assumes exponential time-to-discontinuation with hazard `lambda`,
    calibrated so `S(12) = p12`. The mean of that survival function over the
    year reduces to a closed form with no integration at runtime:

        f = (1 - p12) / (-ln p12)      for 0 < p12 < 1
        f = 1                          for p12 = 1

    Applied per therapy, not globally: the new therapy and its comparators
    may differ materially in discontinuation profile. This is a stated
    simplification — in steady state beyond year one an incident cohort is
    supplemented by the surviving prevalent cohort, so the true fraction
    rises with year, and applying the first-year fraction uniformly across a
    multi-year horizon understates later-year consumption. That conservatism
    is documented in M10's narrative, not corrected here.

    Args:
        p12: proportion of patients still on therapy at 12 months, in (0, 1].

    Returns:
        Treatment-year fraction in (0, 1].

    Raises:
        ValueError: if p12 is not in (0, 1], or is NaN.
    """
    if math.isnan(p12) or not (0 < p12 <= 1):
        raise ValueError(f"p12 must be in (0, 1], got {p12!r}")

    if p12 == 1:
        return 1.0

    if p12 > _LOG1P_THRESHOLD:
        # -ln(p12) = -log1p(p12 - 1); log1p keeps precision for p12 near 1,
        # where log(p12) directly would underflow toward 0 via cancellation.
        neg_ln_p12 = -math.log1p(p12 - 1)
    else:
        neg_ln_p12 = -math.log(p12)

    return (1 - p12) / neg_ln_p12
