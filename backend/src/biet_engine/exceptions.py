"""Engine exception hierarchy — no HTTP knowledge whatsoever.

That is what keeps `biet_engine` pure: `biet_api` maps these to HTTP
responses (biet-backend skill section 8.4), but this module never imports
anything that would let it do so itself. Adding a new engine error means
adding one subclass here, never touching a route.
"""

from __future__ import annotations

from typing import Any, ClassVar


class EngineError(Exception):
    """Base for every engine-raised domain error."""

    code: ClassVar[str] = "ENGINE_ERROR"

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.context = context
        super().__init__(self.message)


class FunnelInvariantError(EngineError):
    """A funnel stage exceeded its predecessor — the funnel is not monotonic."""

    code = "FUNNEL_NOT_MONOTONIC"


class UnresolvedParameterError(EngineError):
    """A required parameter reached the engine unresolved rather than being
    defaulted, so the caller can surface the gap instead of a silently wrong
    answer (M2 section 5.1 — adult_share is the canonical example)."""

    code = "UNRESOLVED_PARAMETER"


class CorrelatedCriteriaError(EngineError):
    """Two enabled eligibility criteria are declared correlated (M3 section
    5.4) — multiplying their marginal factors would understate the joint
    population. Raised only in strict mode; permissive mode (M9's sensitivity
    sweeps) proceeds with a warning instead."""

    code = "CORRELATED_CRITERIA"


class CurrencyMismatchError(EngineError):
    """Two Money values with different currency codes were combined. No
    implicit conversion, ever (M5 section 5.4) — conversion to the reporting
    currency happens once, in M7, using the run's FX snapshot."""

    code = "CURRENCY_MISMATCH"


class UptakeMonotonicityError(EngineError):
    """Uptake decreased year over year without allow_erosion set (M4 section
    5.2). Far more often a data-entry error than genuine competitive
    erosion, so it raises by default rather than being silently accepted."""

    code = "UPTAKE_NOT_MONOTONIC"


class UnknownTherapyError(EngineError):
    """A substitution share names a drug_id that isn't in the therapy set it
    should be drawing from (M4 section 6)."""

    code = "UNKNOWN_THERAPY"


class DisplacementError(EngineError):
    """A displaced share had to be redistributed across the remaining
    therapies, but none of them had any headroom left to absorb it (M4
    section 5.4) — the source-of-business vector is inconsistent with the
    baseline mix in a way redistribution alone can't resolve."""

    code = "DISPLACEMENT_NO_HEADROOM"
