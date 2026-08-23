"""Engine-only constants and closed sets.

Mirrors the domain vocabulary of `biet_api.constants.domain` where the engine
needs the same closed set — the engine cannot import `biet_api` (the pure
package boundary in biet-backend skill section 1), so a small amount of
duplication across the two `constants` modules is the intended design, not a
DRY violation. Keep the *members* identical to `biet_api`'s; a mismatch there
is a real bug (a value that round-trips through both packages would change
meaning), and is exactly what `test_layering.py`'s sibling test for constant
parity should catch if the two ever drift.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class FunnelStage(StrEnum):
    """`funnel.stage` and the M2 funnel order. Order is the funnel order."""

    TOTAL_POPULATION = "total_population"
    ADULT_POPULATION = "adult_population"
    DISEASED = "diseased"
    DIAGNOSED = "diagnosed"
    TREATED = "treated"
    LABEL_ELIGIBLE = "label_eligible"
    ADDRESSABLE = "addressable"


class CriterionType(StrEnum):
    BMI = "bmi"
    COMORBIDITY = "comorbidity"
    HBA1C = "hba1c"
    AGE = "age"
    LINE_OF_THERAPY = "line_of_therapy"
    PRIOR_FAILURE = "prior_failure"


class PriceBasis(StrEnum):
    LIST = "list"
    NADAC = "nadac"
    ESTIMATED_NET = "estimated_net"
    PPP_DERIVED = "ppp_derived"


class UptakeCurve(StrEnum):
    LINEAR = "linear"
    LOGISTIC = "logistic"
    MANUAL = "manual"


#: A rate/factor/probability is a fraction in this half-open-at-zero,
#: closed-at-one interval (CLAUDE.md non-negotiable 5).
RATE_MIN: Final[float] = 0.0
RATE_MAX: Final[float] = 1.0

#: Prevalence must be a fraction strictly between 0 and 1 — 20.64 entered
#: where 0.2064 was meant is the specific unit error this bounds catches
#: (M2 section 5, "prevalence of 20.64 (percent, not fraction) raises").
PREVALENCE_MIN: Final[float] = 0.0
PREVALENCE_MAX: Final[float] = 1.0

#: Logistic uptake curve defaults (M4 section 5.1).
LOGISTIC_DEFAULT_STEEPNESS: Final[float] = 1.2

#: Input shares (sigma, baseline mix) are considered to sum to 1.0 within
#: this tolerance (M4 sections 5.3/5.5) — looser than the accounting check
#: below because these are user/seed-supplied values, not values this module
#: computed itself.
SHARE_SUM_TOLERANCE: Final[float] = 1e-6

#: The engine's own output — uptake plus every m_with — must sum to 1.0
#: within this much tighter tolerance (M4 section 5.6). A violation here is a
#: defect in this module's arithmetic, not a data problem.
ACCOUNTING_TOLERANCE: Final[float] = 1e-9
