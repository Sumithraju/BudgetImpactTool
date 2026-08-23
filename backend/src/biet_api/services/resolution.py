"""The three-level value resolution chain — M1 section 5.2.

Turns reference rows plus scenario overrides into fully-resolved `Valued`
objects carrying provenance, which is what `EngineInput` is assembled from.
This is the boundary the engine sits behind: past this point nothing is
looked up, defaulted or inferred.

Resolution is pure with respect to I/O — it operates on an already-loaded
`ResolutionContext`. The batch loading that fills that context lives in
`repositories/`, which is what keeps section 5.2's "one query per parameter
per market is an N+1 defect" enforceable: there is exactly one place queries
happen, and it is not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from biet_engine.models import ConfidenceTier, Provenance, ResolutionLevel, Valued, Warning_

from ..constants.domain import WarningCode

#: `launch_year - vintage_year` above this emits STALE_VINTAGE (M1 section 5.3).
#: Six triggers it, five does not — the boundary is "> 5", not ">= 5".
STALE_VINTAGE_YEARS = 5

#: An override supplies a value the user asserted rather than one a source
#: published, so it carries tier C — an expert assumption (M1 section 5.2).
OVERRIDE_CONFIDENCE_TIER = ConfidenceTier.C


@dataclass(frozen=True)
class ReferenceValue:
    """One row of resolvable reference data, before provenance is attached."""

    value: float
    source: str
    confidence_tier: ConfidenceTier
    low: float | None = None
    high: float | None = None
    vintage_year: int | None = None
    is_projected: bool = False
    note: str | None = None


#: `(parameter_path, country_code)` — `country_code` None means "all markets".
ResolutionKey = tuple[str, str | None]


@dataclass
class ResolutionContext:
    """Everything resolution needs, batch-loaded once.

    Three stores, most specific first. `scenario_overrides` holds what the
    user set, `country_defaults` the per-market seeded/published values, and
    `global_defaults` the indication-level fallbacks.
    """

    scenario_overrides: Mapping[ResolutionKey, ReferenceValue] = field(default_factory=dict)
    country_defaults: Mapping[ResolutionKey, ReferenceValue] = field(default_factory=dict)
    global_defaults: Mapping[ResolutionKey, ReferenceValue] = field(default_factory=dict)
    launch_year: int = 0


class UnresolvedParameterError(Exception):
    """No level of the chain supplied a value for this path and market.

    Deliberately raised rather than defaulted: M2 section 5.1's `adult_share`
    case is the canonical example of why a silent default here would produce
    a plausible, wrong answer instead of a visible failure.
    """

    def __init__(self, path: str, country_code: str | None) -> None:
        self.path = path
        self.country_code = country_code
        super().__init__(
            f"no value for {path!r} in market {country_code!r} at any resolution level"
        )


class ResolutionService:
    """Resolves parameter paths against a pre-loaded context.

    Warnings accumulate on the instance as values resolve, and travel with
    the result rather than being raised or logged (biet-backend skill
    section 8.6): a stale vintage does not stop a calculation, it qualifies
    one.
    """

    def __init__(self, context: ResolutionContext) -> None:
        self._context = context
        self._warnings: list[Warning_] = []

    @property
    def warnings(self) -> tuple[Warning_, ...]:
        return tuple(self._warnings)

    def resolve(self, path: str, country_code: str | None = None) -> Valued:
        """The most specific value for `path` in `country_code`.

        Order is scenario override, then country default, then global
        default; within each level, a value naming this market beats one
        that applies to all markets. So a scenario override with
        `country_code = None` applies everywhere, but is still beaten by a
        scenario override naming this market explicitly (section 5.2).

        Raises:
            UnresolvedParameterError: no level supplied a value.
        """
        for level, store in (
            (ResolutionLevel.SCENARIO_OVERRIDE, self._context.scenario_overrides),
            (ResolutionLevel.COUNTRY_OVERRIDE, self._context.country_defaults),
            (ResolutionLevel.GLOBAL_DEFAULT, self._context.global_defaults),
        ):
            hit = store.get((path, country_code))
            if hit is None:
                hit = store.get((path, None))
            if hit is not None:
                return self._to_valued(path, country_code, hit, level)

        raise UnresolvedParameterError(path, country_code)

    def _to_valued(
        self,
        path: str,
        country_code: str | None,
        reference: ReferenceValue,
        level: ResolutionLevel,
    ) -> Valued:
        tier = (
            OVERRIDE_CONFIDENCE_TIER
            if level is ResolutionLevel.SCENARIO_OVERRIDE
            else reference.confidence_tier
        )
        self._emit_warnings(path, country_code, reference, tier)

        return Valued(
            value=reference.value,
            low=reference.low,
            high=reference.high,
            provenance=Provenance(
                source=reference.source,
                vintage_year=reference.vintage_year,
                confidence_tier=tier,
                resolution_level=level,
                is_projected=reference.is_projected,
                note=reference.note,
            ),
        )

    def _emit_warnings(
        self,
        path: str,
        country_code: str | None,
        reference: ReferenceValue,
        tier: ConfidenceTier,
    ) -> None:
        """Section 5.3's warning table."""
        if (
            reference.vintage_year is not None
            and self._context.launch_year - reference.vintage_year > STALE_VINTAGE_YEARS
        ):
            self._add(
                WarningCode.STALE_VINTAGE,
                f"{path} uses a {reference.vintage_year} value against a "
                f"{self._context.launch_year} launch",
                country_code, path,
            )

        if reference.is_projected:
            self._add(
                WarningCode.PROJECTED_VALUE,
                f"{path} is projected forward, not observed",
                country_code, path,
            )

        if tier is ConfidenceTier.D:
            self._add(
                WarningCode.TIER_D_INPUT,
                f"{path} is a tier-D placeholder and must be replaced before this "
                "result is relied on",
                country_code, path,
            )

    def _add(
        self, code: WarningCode, message: str, country_code: str | None, path: str,
    ) -> None:
        warning = Warning_(
            code=code.value, message=message,
            country_code=country_code, parameter_path=path,
        )
        if warning not in self._warnings:
            self._warnings.append(warning)
