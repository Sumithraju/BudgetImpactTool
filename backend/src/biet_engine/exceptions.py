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
