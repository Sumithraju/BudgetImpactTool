"""Shared contracts used across every engine module.

Defined once here per docs/modules/README.md ("Shared contracts") — no module
redefines its own `Provenance` or `Money`. Frozen: engine models are immutable
once constructed, since a calculation input must not change under the
calculation that consumes it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from .constants import RATE_MAX, RATE_MIN, CriterionType, FunnelStage, PriceBasis


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


def _validate_rate(v: Valued, *, field_name: str) -> Valued:
    if not (RATE_MIN < v.value <= RATE_MAX):
        raise ValueError(
            f"{field_name} must be a fraction in ({RATE_MIN}, {RATE_MAX}], got {v.value!r} "
            "(a value like 60 where 0.60 was meant is the usual cause)"
        )
    return v


# --------------------------------------------------------------------------- M2 — Population Funnel


class FunnelRates(BaseModel):
    model_config = ConfigDict(frozen=True)

    diagnosis_rate: Valued
    treatment_rate: Valued
    access_rate: Valued

    @field_validator("diagnosis_rate", "treatment_rate", "access_rate")
    @classmethod
    def _rate_in_range(cls, v: Valued, info: ValidationInfo) -> Valued:
        return _validate_rate(v, field_name=info.field_name or "rate")


class FunnelStageResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: FunnelStage
    value: float
    factor: float | None                     # None for the first stage
    provenance: Provenance | None


class FunnelResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    year: int                                # launch-relative, 1-indexed
    stages: tuple[FunnelStageResult, ...]

    @property
    def addressable(self) -> float:
        return self.stages[-1].value


# --------------------------------------------------------------------------- M3 — Eligibility & Segmentation


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str                                # "bmi_ge_30", "cv_comorbidity"
    label: str
    type: CriterionType
    factor: Valued                           # in (0, 1]
    enabled: bool
    correlated_with: tuple[str, ...] = ()

    @field_validator("factor")
    @classmethod
    def _factor_in_range(cls, v: Valued) -> Valued:
        return _validate_rate(v, field_name="factor")


# --------------------------------------------------------------------------- M5 — Cost & Pricing


class Regimen(BaseModel):
    model_config = ConfigDict(frozen=True)

    units_per_admin: Valued
    admins_per_year: Valued
    wastage_pct: Valued                      # [0, 1)


class TherapyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    name: str
    is_new: bool
    regimen: Regimen
    unit_price: Money                        # local currency, per unit
    price_basis: PriceBasis
    discount_pct: Valued                     # [0, 1) — gross-to-net
    admin_cost: Money
    monitoring_cost: Money
    ae_cost: Money
    offset: Money                            # avoided-event savings, subtracted
    persistence_12m: Valued                  # consumed by M6, carried here


# --------------------------------------------------------------------------- M1 — Scenario Workspace


class CountryInput(BaseModel):
    """One market's fully-resolved engine input.

    No optional fields, no defaults (biet-backend skill section 3) — with one
    deliberate exception. `adult_share` is typed nullable because M2 section
    5.1 requires the *unresolved* state to reach the engine explicitly so it
    can raise `UnresolvedParameterError` rather than the resolution layer
    silently defaulting it to 1.0 before the engine ever sees it. Every other
    field is resolved before construction, per the general rule.
    """

    model_config = ConfigDict(frozen=True)

    country_code: str
    currency: str
    population_total: Valued
    adult_share: Valued | None
    population_growth: Valued
    prevalence: Valued
    health_exp_pc: Valued
    gdp_pc_ppp: Valued
    funnel: FunnelRates                      # M2
    criteria: tuple[Criterion, ...]          # M3
    therapies: tuple[TherapyInput, ...]      # M5
    new_therapy: TherapyInput
