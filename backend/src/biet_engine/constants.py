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


class ConfidenceTier(StrEnum):
    """How much weight a resolved value carries.

    Lives here rather than in `models.py` because it is a closed set (this
    module's stated purpose) and because `constants` must be importable
    without `models` — `TIER_RELATIVE_STANDARD_ERROR` below is keyed by it.
    `models` re-exports it so existing `from .models import ConfidenceTier`
    imports keep working.
    """

    A = "A"   # published, country-specific, with stated interval
    B = "B"   # published, regional or extrapolated
    C = "C"   # analogue-derived or expert assumption
    D = "D"   # placeholder requiring replacement


class ResolutionLevel(StrEnum):
    GLOBAL_DEFAULT = "global_default"
    COUNTRY_OVERRIDE = "country_override"
    SCENARIO_OVERRIDE = "scenario_override"


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


class CostComponent(StrEnum):
    """The parts an annual therapy cost is built from (M5 section 5.5).

    Named as a closed set because M13's cost bridge decomposes the net cost
    per patient switched across exactly these, and the decomposition is only
    exact if it covers all of them and nothing else.
    """

    ACQUISITION = "acquisition"
    ADMIN = "admin"
    MONITORING = "monitoring"
    AE = "ae"
    OFFSET = "offset"


class PriceBasis(StrEnum):
    LIST = "list"
    NADAC = "nadac"
    ESTIMATED_NET = "estimated_net"
    PPP_DERIVED = "ppp_derived"


class UptakeCurve(StrEnum):
    LINEAR = "linear"
    LOGISTIC = "logistic"
    MANUAL = "manual"


class AffordabilityBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class SolverMethod(StrEnum):
    ANALYTIC = "analytic"
    BISECTION = "bisection"


#: A rate/factor/probability is a fraction in this half-open-at-zero,
#: closed-at-one interval (CLAUDE.md non-negotiable 5).
#: M14. Interval from a trial's primary completion to approval, for a
#: priority-review asset with a clean readout — optimistic for anything else,
#: and a sensitivity lever rather than a fact.
REGULATORY_LAG_YEARS: Final[float] = 1.5

#: M14. Ceiling on the combined share of modelled pipeline entrants. Without
#: it an unbounded entrant total drives incumbent shares to zero and leaves a
#: world-without consisting entirely of drugs that do not yet exist, which is
#: not a market and not a comparison.
MAX_ENTRANT_TOTAL_SHARE: Final[float] = 0.60

#: M14. Years from entry to plateau, when a scenario does not say.
ENTRANT_DEFAULT_RAMP_YEARS: Final[int] = 3

#: Weeks in a year, for annualising an incidence observed over a trial's
#: exposure window (ARCHITECTURE.md section 5.10). A 68-week incidence quoted
#: as an annual rate overstates it; a 26-week one understates it.
WEEKS_PER_YEAR: Final[float] = 52.0

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

#: Cumulative affordability ratio thresholds (M8 section 5.1). A market's
#: band is the highest threshold its ratio meets or exceeds; below the
#: lowest, it's LOW.
AFFORDABILITY_THRESHOLDS: Final[dict[AffordabilityBand, float]] = {
    AffordabilityBand.MODERATE: 0.001,
    AffordabilityBand.HIGH: 0.005,
    AffordabilityBand.CRITICAL: 0.01,
}

#: Cross-market PPP price derivation defaults (M5 section 5.3 / M8 section 5.3).
PPP_DEFAULT_ELASTICITY: Final[float] = 1.0
PPP_PRICE_FLOOR: Final[float] = 0.05

#: Reverse solver numerics (M8 section 5.5).
SOLVER_RELATIVE_TOLERANCE: Final[float] = 1e-6
SOLVER_MAX_ITERATIONS: Final[int] = 100
SOLVER_BRACKET_MULTIPLIER: Final[float] = 10.0
SOLVER_BRACKET_WIDEN_MULTIPLIER: Final[float] = 100.0

#: The reference market for cross-market PPP price derivation (M5 section 5.3).
REFERENCE_MARKET: Final[str] = "USA"

#: Normal approximation to a 95% interval: SD = (high - low) / 3.92
#: (M9 section 5.2).
CI_TO_SD_DIVISOR: Final[float] = 3.92

#: Confidence-tier default relative standard error, used for OWSA ranges and
#: PSA spread where no published interval exists (M9 section 5.1/5.2). Tier A
#: means "as published" — it has a real interval, so its entry here is only a
#: fallback for an A-tier value that somehow arrives without one. These are
#: conventions, not empirical estimates (section 12), and live here so they
#: can be re-based without touching logic.
TIER_RELATIVE_STANDARD_ERROR: Final[dict[ConfidenceTier, float]] = {
    ConfidenceTier.A: 0.05,
    ConfidenceTier.B: 0.15,
    ConfidenceTier.C: 0.30,
    ConfidenceTier.D: 0.50,
}

#: OWSA fallback range where neither a published interval nor a tier default
#: applies (M9 section 5.1).
OWSA_DEFAULT_VARIATION: Final[float] = 0.20

#: PSA defaults (M9 section 5.2/5.4) and its validated bounds (section 6).
PSA_DEFAULT_ITERATIONS: Final[int] = 5_000
PSA_DEFAULT_SEED: Final[int] = 20_260_906
PSA_MIN_ITERATIONS: Final[int] = 100
PSA_MAX_ITERATIONS: Final[int] = 50_000

#: PSA convergence: the running mean over the final 10% of iterations must be
#: within 1% of the overall mean (M9 section 5.5).
PSA_CONVERGENCE_TAIL_FRACTION: Final[float] = 0.10
PSA_CONVERGENCE_TOLERANCE: Final[float] = 0.01

#: Fraction of sampled draws that may be clipped to their domain before it
#: stops being routine and warrants a warning (M9 section 6).
PSA_CLIP_WARNING_FRACTION: Final[float] = 0.01
