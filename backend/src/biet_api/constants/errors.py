"""Error codes — a shared registry, exported to the frontend.

Both sides speak the same vocabulary, so a code is never invented inline
(biet-backend skill section 8.2). Engine codes are mirrored here because the
API maps `biet_engine.exceptions` onto HTTP responses and the frontend needs
to recognise them; the engine itself imports nothing from this module.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    # --- API layer ---
    INTERNAL = "INTERNAL_ERROR"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UNKNOWN_PARAMETER_PATH = "UNKNOWN_PARAMETER_PATH"
    PARAMETER_OUT_OF_RANGE = "PARAMETER_OUT_OF_RANGE"
    COMPARATOR_NOT_PRICED = "COMPARATOR_NOT_PRICED"

    # --- mirrored from biet_engine.exceptions ---
    FUNNEL_NOT_MONOTONIC = "FUNNEL_NOT_MONOTONIC"
    UNRESOLVED_PARAMETER = "UNRESOLVED_PARAMETER"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    CORRELATED_CRITERIA = "CORRELATED_CRITERIA"
    UPTAKE_NOT_MONOTONIC = "UPTAKE_NOT_MONOTONIC"
    UNKNOWN_THERAPY = "UNKNOWN_THERAPY"
    DISPLACEMENT_NO_HEADROOM = "DISPLACEMENT_NO_HEADROOM"
    MISSING_FX_RATE = "MISSING_FX_RATE"
    SOLVER_INVARIANT_VIOLATED = "SOLVER_INVARIANT_VIOLATED"
    UNPRICED_REFERENCE = "UNPRICED_REFERENCE"
