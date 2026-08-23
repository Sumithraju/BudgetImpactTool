"""Shared contracts used across every engine module.

Defined once here per docs/modules/README.md ("Shared contracts") — no module
redefines its own `Provenance` or `Money`. Frozen: engine models are immutable
once constructed, since a calculation input must not change under the
calculation that consumes it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceTier(StrEnum):
    A = "A"   # published, country-specific, with stated interval
    B = "B"   # published, regional or extrapolated
    C = "C"   # analogue-derived or expert assumption
    D = "D"   # placeholder requiring replacement


class ResolutionLevel(StrEnum):
    GLOBAL_DEFAULT = "global_default"
    COUNTRY_OVERRIDE = "country_override"
    SCENARIO_OVERRIDE = "scenario_override"


class Provenance(BaseModel):
    """Travels with every resolved value. Never dropped by any transform."""

    model_config = ConfigDict(frozen=True)

    source: str                              # "WHO NCD_BMI_30A"
    vintage_year: int | None = None
    confidence_tier: ConfidenceTier
    resolution_level: ResolutionLevel
    is_projected: bool = False
    note: str | None = None


class Valued(BaseModel):
    """A number with its provenance and, where published, its interval."""

    model_config = ConfigDict(frozen=True)

    value: float
    low: float | None = None                 # 95% lower bound, where published
    high: float | None = None                # 95% upper bound
    provenance: Provenance


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: float                            # float inside the engine; Decimal at the boundary
    currency: str = Field(min_length=3, max_length=3)


class Warning_(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                                # STALE_VINTAGE | TIER_D_INPUT | ...
    message: str
    country_code: str | None = None
    parameter_path: str | None = None
