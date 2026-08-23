"""Shared contracts used across every engine module.

Defined once here per docs/modules/README.md ("Shared contracts") — no module
redefines its own `Provenance` or `Money`. Frozen: engine models are immutable
once constructed, since a calculation input must not change under the
calculation that consumes it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from .constants import (
    RATE_MAX,
    RATE_MIN,
    SHARE_SUM_TOLERANCE,
    AffordabilityBand,
    ConfidenceTier,
    CriterionType,
    FunnelStage,
    PriceBasis,
    ResolutionLevel,
    SolverMethod,
    UptakeCurve,
)
from .exceptions import CurrencyMismatchError

# Re-exported: both are closed sets and now live in `constants` (which must
# not import this module), but they were part of this module's public surface
# first and docs/modules/README.md documents them as shared contracts here.
__all__ = ["ConfidenceTier", "ResolutionLevel"]


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
    """Amount and currency travel together, always. Arithmetic between two
    `Money` values of different currencies is not a conversion error to catch
    later — it is a defect to reject immediately (M5 section 5.4)."""

    model_config = ConfigDict(frozen=True)

    amount: float                            # float inside the engine; Decimal at the boundary
    currency: str = Field(min_length=3, max_length=3)

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency} with {other.currency}",
                currency_a=self.currency, currency_b=other.currency,
            )

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, scalar: float) -> Money:
        return Money(amount=self.amount * scalar, currency=self.currency)


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


class CriteriaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    combined_factor: Valued
    applied: tuple[Criterion, ...]           # enabled only, in application order
    # Not in the module doc's abbreviated contract snippet, but required to
    # fulfil section 5.4's own description of permissive mode ("emits a
    # CORRELATED_CRITERIA warning and proceeds"): a pure function has no other
    # way to surface a non-fatal condition than returning it (biet-backend
    # skill section 8.6 — warnings are never raised, never only logged).
    warnings: tuple[Warning_, ...] = ()


# --------------------------------------------------------------------------- M5 — Cost & Pricing


def _validate_half_open_unit_interval(v: Valued, *, field_name: str) -> Valued:
    if not (0 <= v.value < 1):
        raise ValueError(f"{field_name} must be in [0, 1), got {v.value!r}")
    return v


class Regimen(BaseModel):
    model_config = ConfigDict(frozen=True)

    units_per_admin: Valued
    admins_per_year: Valued
    wastage_pct: Valued                      # [0, 1)

    @field_validator("admins_per_year")
    @classmethod
    def _admins_per_year_positive(cls, v: Valued) -> Valued:
        if v.value <= 0:
            raise ValueError(f"admins_per_year must be > 0, got {v.value!r}")
        return v

    @field_validator("wastage_pct")
    @classmethod
    def _wastage_in_range(cls, v: Valued) -> Valued:
        return _validate_half_open_unit_interval(v, field_name="wastage_pct")


class TherapyInput(BaseModel):
    """One therapy's fully-resolved cost inputs for one market.

    `price_provenance` is not in M5's own abbreviated contract snippet, but
    `unit_price` is typed `Money` (amount + currency only, no provenance
    field), and `TherapyCost.provenance` has to come from somewhere — the
    price's origin (source, confidence tier, whether it's PPP-derived) is
    the most decision-relevant provenance a cost figure carries.
    """

    model_config = ConfigDict(frozen=True)

    drug_id: int
    name: str
    is_new: bool
    regimen: Regimen
    unit_price: Money                        # local currency, per unit
    price_basis: PriceBasis
    price_provenance: Provenance
    discount_pct: Valued                     # [0, 1) — gross-to-net
    admin_cost: Money
    monitoring_cost: Money
    ae_cost: Money
    offset: Money                            # avoided-event savings, subtracted
    persistence_12m: Valued                  # consumed by M6, carried here

    @field_validator("unit_price")
    @classmethod
    def _unit_price_positive(cls, v: Money) -> Money:
        if v.amount <= 0:
            raise ValueError(f"unit_price must be > 0, got {v.amount!r}")
        return v

    @field_validator("discount_pct")
    @classmethod
    def _discount_in_range(cls, v: Valued) -> Valued:
        return _validate_half_open_unit_interval(v, field_name="discount_pct")

    @field_validator("offset")
    @classmethod
    def _offset_non_negative(cls, v: Money) -> Money:
        if v.amount < 0:
            raise ValueError(
                f"offset must not be negative, got {v.amount!r} — an avoided "
                "cost entered as negative is the usual cause"
            )
        return v


class TherapyCost(BaseModel):
    model_config = ConfigDict(frozen=True)

    drug_id: int
    country_code: str
    acquisition: Money
    admin: Money
    monitoring: Money
    ae: Money
    offset: Money
    total: Money                             # annual cost per full treated patient-year
    price_basis: PriceBasis
    provenance: Provenance


# --------------------------------------------------------------------------- M4 — Uptake & Market Mix


class UptakeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    curve: UptakeCurve
    year_1: Valued | None = None             # linear
    terminal: Valued | None = None           # linear, logistic plateau
    steepness: Valued | None = None          # logistic k
    inflection_year: Valued | None = None    # logistic y_mid
    vector: tuple[float, ...] | None = None  # manual
    allow_erosion: bool = False


class Substitution(BaseModel):
    """`shares` maps `drug_id -> sigma`; must sum to 1.0 (M4 section 5.3)."""

    model_config = ConfigDict(frozen=True)

    shares: Mapping[int, Valued]

    @field_validator("shares")
    @classmethod
    def _shares_valid(cls, v: Mapping[int, Valued]) -> Mapping[int, Valued]:
        negative = [drug_id for drug_id, s in v.items() if s.value < 0]
        if negative:
            raise ValueError(f"substitution shares must not be negative: {negative}")
        total = sum(s.value for s in v.values())
        if abs(total - 1.0) > SHARE_SUM_TOLERANCE:
            raise ValueError(f"substitution shares must sum to 1.0, got {total!r}")
        return v


class MarketMix(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    year: int
    uptake: float                            # u(y), share of addressable
    shares_without: Mapping[int, float]      # drug_id -> m_without, sums to 1.0
    shares_with: Mapping[int, float]         # drug_id -> m_with; + uptake sums to 1.0
    # Not in the module doc's abbreviated contract snippet — required for the
    # same reason M3's CriteriaResult and M5's TherapyInput each needed one
    # field beyond theirs: section 5.4 requires a SUBSTITUTION_FLOOR warning
    # whenever displacement redistribution occurs, and a pure function has no
    # other channel to surface that (biet-backend skill section 8.6).
    warnings: tuple[Warning_, ...] = ()


# --------------------------------------------------------------------------- M1 — Scenario Workspace


class CountryInput(BaseModel):
    """One market's fully-resolved engine input.

    No optional fields, no defaults (biet-backend skill section 3) — with two
    deliberate exceptions. `adult_share` is typed nullable because M2 section
    5.1 requires the *unresolved* state to reach the engine explicitly so it
    can raise `UnresolvedParameterError` rather than the resolution layer
    silently defaulting it to 1.0 before the engine ever sees it. `health_exp_pc`
    is nullable for the identical reason, per M8 section 6 ("Missing
    health_exp_pc for a market -> raise UnresolvedParameterError"). Every
    other field is resolved before construction, per the general rule.
    """

    model_config = ConfigDict(frozen=True)

    country_code: str
    currency: str
    population_total: Valued
    adult_share: Valued | None
    population_growth: Valued
    prevalence: Valued
    health_exp_pc: Valued | None              # USD per capita (M0's health_exp_pc_usd)
    gdp_pc_ppp: Valued
    funnel: FunnelRates                      # M2
    criteria: tuple[Criterion, ...]          # M3
    therapies: tuple[TherapyInput, ...]      # M5, T — excludes new_therapy
    new_therapy: TherapyInput
    # Not in M1's own abbreviated CountryInput snippet, but M7's formula
    # (section 5.1) references m_without(t,y) and sigma_t directly, and
    # nothing else on this model carries them — M4's build_market_mix already
    # takes exactly this shape as its `baseline`/`substitution` parameters.
    baseline_shares: Mapping[int, tuple[float, ...]]   # drug_id -> per-year m_without
    substitution: Substitution                          # M4, sigma


class EngineInput(BaseModel):
    """Everything one calculation run needs, fully resolved. No optional
    fields, no defaults — this is the boundary past which nothing is looked
    up (M1's contract, docs/modules/README.md "Shared contracts")."""

    model_config = ConfigDict(frozen=True)

    scenario_id: UUID
    indication_id: int
    launch_year: int
    horizon_years: int = Field(ge=1, le=5)
    reporting_currency: str
    fx_rates: Mapping[str, float]
    # Not in M1's own abbreviated EngineInput snippet. CLAUDE.md non-negotiable
    # 6 — "FX is snapshotted into the run" — implies the snapshot has a
    # vintage; M7's EngineResult.fx_snapshot_date has to come from the input
    # it's reporting on, not be invented at calculation time.
    fx_snapshot_date: date
    uptake: UptakeInput                                 # M4 — one trajectory, all markets
    countries: tuple[CountryInput, ...]


# --------------------------------------------------------------------------- M7 — Budget Impact Calculator


class YearResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    year: int                                # launch-relative, 1-indexed
    calendar_year: int                       # launch_year + year - 1, display only
    uptake: float
    addressable: float
    patients_on_new: float
    cost_without: Money                      # local currency
    cost_with: Money
    budget_impact: Money
    impact_per_patient: Money | None         # None when patients_on_new == 0
    # Not in M7's own abbreviated contract snippet, but section 5.2 is
    # explicit that this must be "expose[d]... in the response; it is the
    # single most explanatory number in the model" — and section 9 names a
    # dedicated frontend component for it (NetCostPerSwitchCard).
    net_cost_per_switch: Money               # local currency, section 5.2's bracketed term


class CountryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    currency: str
    funnel: FunnelResult                     # year 1's funnel — years[].addressable carries the rest
    years: tuple[YearResult, ...]
    cumulative_budget_impact: Money


class Totals(BaseModel):
    """Cross-market aggregation, in the reporting currency — not in M7's
    abbreviated contract snippet (which references `Totals` without defining
    it), but section 5.6 fully specifies the three quantities it must hold."""

    model_config = ConfigDict(frozen=True)

    by_year: tuple[Money, ...]               # Total(y)
    cumulative: Money
    peak_year: int                           # argmax Total(y); ties resolve to the earliest


class EngineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine_version: str
    reporting_currency: str
    fx_snapshot_date: date
    countries: tuple[CountryResult, ...]
    totals: Totals                           # reporting currency
    warnings: tuple[Warning_, ...]


# --------------------------------------------------------------------------- M8 — Affordability & Price Solver


class CountryAffordability(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    health_budget: Money                     # local currency
    ratio_by_year: tuple[float, ...]
    cumulative_ratio: float
    band: AffordabilityBand
    pmpy: Money | None = None                # plan-level markets only


class CorridorEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str
    max_unit_price_usd: float | None         # None when infeasible or unbounded
    max_annual_acquisition_usd: float | None
    feasible: bool
    unbounded: bool
    method: SolverMethod
    iterations: int | None = None
    # Not in M8's own abbreviated contract snippet. Section 5.6 requires
    # infeasibility to "report the shortfall sum(beta) - tau*sum(H)" — this
    # is the only place in the response shape for that number to live.
    shortfall_usd: float | None = None       # only set when infeasible via the analytic path


class PriceCorridor(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_ratio: float
    entries: tuple[CorridorEntry, ...]
    binding_market: str | None
    single_global_price_ceiling_usd: float | None
    # Not in M8's own abbreviated contract snippet, same reasoning as every
    # other warnings field added so far (M3/M4/M5/M7): section 6 requires a
    # diagnostic when tau > 1, and section 5.6 requires one when sum(alpha) =
    # 0 (unbounded) — a pure function has no other channel to surface either.
    warnings: tuple[Warning_, ...] = ()


# --------------------------------------------------------------------------- M9 — Uncertainty & Sensitivity


class SensitivityParam(BaseModel):
    """One parameter to sweep in OWSA.

    Not defined in M9's contract snippet (which references the type without
    declaring it), so it's built from section 5.1's own description: a
    parameter is identified by its dotted path, carries a label for the
    tornado chart, and has a base value plus the low/high bounds the sweep
    evaluates at.
    """

    model_config = ConfigDict(frozen=True)

    parameter_path: str
    label: str
    base_value: float
    low_value: float
    high_value: float


class OwsaEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    parameter_path: str
    label: str
    base_value: float
    low_value: float
    high_value: float
    result_at_low: float                     # cumulative BI, reporting currency
    result_at_high: float
    swing: float                             # abs(high - low)
    rank: int


class OwsaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_result: float
    entries: tuple[OwsaEntry, ...]           # sorted by descending swing
    warnings: tuple[Warning_, ...] = ()


class PsaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    iterations: int
    seed: int
    mean: float
    median: float
    p2_5: float
    p97_5: float
    samples: tuple[float, ...]               # for the histogram/CDF
    exceedance: Mapping[str, float]          # band name -> P(ratio > threshold)
    converged: bool
    warnings: tuple[Warning_, ...] = ()


# --------------------------------------------------------------------------- M10 — Evidence, Narrative & Export


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: int
    document_title: str
    issuing_body: str                        # ISPOR | NICE | WHO | CDA-AMC
    section: str | None
    page_number: int | None
    text: str
    similarity: float


class AssumptionEntry(BaseModel):
    """One row of section 5.7's assumption register.

    Not in M10's own contract snippet, which describes the register as "a
    table of every resolved input: parameter path, market, value, source,
    vintage, confidence tier and resolution level" without declaring a type
    for it. Those seven columns are exactly the fields here.
    """

    model_config = ConfigDict(frozen=True)

    parameter_path: str
    country_code: str
    value: float
    source: str
    vintage_year: int | None
    confidence_tier: ConfidenceTier
    resolution_level: ResolutionLevel
    is_projected: bool


class Narrative(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    sections: Mapping[str, str]              # population | impact | ... | limitations
    citations: tuple[RetrievedChunk, ...]
    model_id: str
    generated_at: datetime
