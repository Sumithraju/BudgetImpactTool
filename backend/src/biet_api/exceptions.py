"""API-layer exception hierarchy — the backend standards, section 8.1.

Every error carries its own code and HTTP status, so route handlers never
construct an HTTP error themselves: they raise a domain exception and the
centralised handlers (registered once in `main.py`, Phase 3) map it. Adding
a new error means adding one subclass here.

Distinct from `biet_engine.exceptions`, which knows nothing about HTTP —
that is what keeps the engine pure.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .constants.errors import ErrorCode


class BietError(Exception):
    """Base for every API-layer domain error."""

    code: ClassVar[str] = ErrorCode.INTERNAL
    status_code: ClassVar[int] = 500

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.context = context
        super().__init__(self.message)


class EntityNotFoundError(BietError):
    """The requested resource does not exist."""

    code = ErrorCode.ENTITY_NOT_FOUND
    status_code = 404


class ValidationError(BietError):
    """The request is well-formed but semantically invalid."""

    code = ErrorCode.VALIDATION_FAILED
    status_code = 422


class UnknownParameterPathError(ValidationError):
    """An override names a path outside the closed vocabulary (M1 section 5.1)."""

    code = ErrorCode.UNKNOWN_PARAMETER_PATH


class ParameterOutOfRangeError(ValidationError):
    """An override value falls outside the range its path permits."""

    code = ErrorCode.PARAMETER_OUT_OF_RANGE


class ComparatorNotPricedError(ValidationError):
    """A scenario names a comparator that has no price or regimen (M12 section 5.6).

    Raised rather than dropping the comparator from the market mix. A
    comparator absent from the world-without never has its cost subtracted,
    so budget impact is overstated by exactly the cost of the care the new
    therapy displaces — a wrong number that looks entirely reasonable.
    """

    code = ErrorCode.COMPARATOR_NOT_PRICED


class ConflictError(BietError):
    """The operation conflicts with the current state."""

    code = ErrorCode.CONFLICT
    status_code = 409


class UpstreamUnavailableError(BietError):
    """A required external service is unavailable."""

    code = ErrorCode.UPSTREAM_UNAVAILABLE
    status_code = 503
