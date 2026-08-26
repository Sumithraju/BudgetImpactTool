"""Calculation response contracts — ARCHITECTURE.md section 10.5.

These mirror `biet_engine`'s result models rather than re-exporting them.
The engine's models are frozen calculation outputs; these are the HTTP
contract, and the two drift apart deliberately — the response rounds for
display, flattens `Money` into amount plus currency, and carries provenance
in the shape the interface needs.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceRead(BaseModel):
    source: str
    vintage_year: int | None = None
    confidence_tier: str
    resolution_level: str
    is_projected: bool = False
    note: str | None = None


class ValuedRead(BaseModel):
    value: float
    low: float | None = None
    high: float | None = None
    provenance: ProvenanceRead


class WarningRead(BaseModel):
    code: str
    message: str
    country_code: str | None = None
    parameter_path: str | None = None


class FunnelStageRead(BaseModel):
    stage: str
    value: float
    factor: float | None
    provenance: ProvenanceRead | None


class YearRead(BaseModel):
    year: int
    calendar_year: int
    uptake: float
    addressable: float
    patients_on_new: float
    cost_without: float
    cost_with: float
    budget_impact: float
    net_cost_per_switch: float
    impact_per_patient: float | None


class CriterionRead(BaseModel):
    code: str
    label: str
    factor: float
    enabled: bool
    correlated_with: list[str] = Field(default_factory=list)


class TherapyRead(BaseModel):
    drug_id: int
    name: str
    is_new: bool
    unit_price: float
    currency: str
    price_basis: str
    provenance: ProvenanceRead
    persistence_12m: float


class AffordabilityRead(BaseModel):
    cumulative_ratio: float
    band: str
    health_budget: float
    pmpy: float | None = None


class BridgeTermRead(BaseModel):
    """One component's contribution to the net cost per patient switched."""

    component: str
    new_therapy: float
    displaced: float
    delta: float


class CostBridgeRead(BaseModel):
    """M13 section 5.3. The terms sum to `net_cost_per_switch` exactly.

    The answer to what a payer actually asks: not what the new therapy costs,
    but of the difference, how much is price and how much is everything else.
    """

    terms: list[BridgeTermRead]
    net_cost_per_switch: float


class CountryRead(BaseModel):
    country_code: str
    currency: str
    cumulative_budget_impact: float
    funnel: list[FunnelStageRead]
    years: list[YearRead]
    criteria: list[CriterionRead]
    therapies: list[TherapyRead]
    new_therapy: TherapyRead
    affordability: AffordabilityRead | None = None
    #: Year-invariant: persistence, substitution and unit costs do not vary
    #: by year, so one bridge explains every year's net cost per switch.
    cost_bridge: CostBridgeRead | None = None
    #: M16. What the spend buys in this market. Absent when no treatment
    #: effect is published for the asset, which the warnings say explicitly.
    outcomes: OutcomesRead | None = None
    #: M17. The payer's own denominator, applied to this market.
    payer: PayerViewRead | None = None
    #: The prevalence/incidence block and the funnel with its arithmetic shown.
    epidemiology: EpidemiologyRead | None = None


# --------------------------------------------------------------------------- M16 outcomes


class AvoidedEventRead(BaseModel):
    """One event class, and what avoiding it is worth.

    `events_without_by_year` is the count on current care and `avoided_by_year`
    the reduction the therapy is credited with — reported separately rather
    than as a percentage, because a 20% reduction on a 0.3% annual rate and the
    same reduction on a 2.4% one are the same statistic and completely
    different findings.
    """

    event_class: str
    label: str
    trial: str
    baseline_annual_rate: float
    relative_reduction: float
    events_without_by_year: list[float]
    avoided_by_year: list[float]
    cost_avoided_by_year: list[float]
    total_avoided: float
    total_cost_avoided: float
    baseline_provenance: ProvenanceRead
    effect_provenance: ProvenanceRead


class OutcomesRead(BaseModel):
    """What the spend buys, in one market.

    `responders_by_year` is None rather than zero when no response profile was
    published for the therapy. An absence of evidence and a finding of no
    responders are different claims and this contract keeps them apart.
    """

    country_code: str
    currency: str
    responders_by_year: list[float] | None = None
    mean_weight_loss_pct: float | None = None
    responder_threshold: str | None = None
    responder_trial: str | None = None
    regain_per_year: float | None = None
    events: list[AvoidedEventRead] = Field(default_factory=list)
    total_cost_avoided: float = 0.0
    total_cost_avoided_by_year: list[float] = Field(default_factory=list)
    warnings: list[WarningRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- M17 payer views


class PayerViewRead(BaseModel):
    """The figures a payer conversation opens with — M17 sections 5.1-5.3.

    `covered_population_is_assumed` is not a footnote. An insurer reading a
    PMPM computed against the national population is reading a number roughly
    two orders of magnitude too small, and the only defence against that is
    saying, on the figure itself, which denominator produced it.
    """

    perspective: str
    perspective_label: str
    currency: str
    covered_population: float
    covered_population_is_assumed: bool
    pmpm_by_year: list[float]
    pmpy_by_year: list[float]
    cumulative_pmpm: float
    patients_treated_by_year: list[float]
    cost_per_treated_patient: float
    total_cost_current_care: list[float]
    total_cost_with_intervention: list[float]


class UptakeCaseRead(BaseModel):
    """The same scenario at low, medium and high adoption — M17 section 5.5."""

    case: str
    label: str
    multiplier: float
    uptake_terminal: float
    by_year: list[float]
    cumulative: float
    peak_year: int
    patients_treated_final_year: float
    currency: str


class UptakeScenarioResponse(BaseModel):
    scenario_id: uuid.UUID
    currency: str
    cases: list[UptakeCaseRead]
    warnings: list[WarningRead] = Field(default_factory=list)


class BreakEvenRead(BaseModel):
    """The price at which incremental budget impact is zero — M17 section 5.4.

    Distinct from M8's corridor, which solves to an affordability *target*.
    Break-even is the target of zero: the price at which the new therapy costs
    the payer exactly what the care it displaces costs today. Above it the
    asset adds budget; below it, it saves.
    """

    country_code: str
    currency: str
    current_unit_price: float
    break_even_unit_price: float | None
    current_annual_cost: float
    break_even_annual_cost: float | None
    headroom_pct: float | None
    feasible: bool
    method: str
    note: str | None = None


class BreakEvenResponse(BaseModel):
    scenario_id: uuid.UUID
    entries: list[BreakEvenRead]
    warnings: list[WarningRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- M18 subgroups


class SubgroupResultRead(BaseModel):
    """One segment's contribution to the total.

    Reported alongside the aggregate rather than instead of it. The aggregate
    answers what the asset costs; this answers where the cost is concentrated,
    and those are different questions a formulary committee asks in sequence.
    """

    subgroup_code: str
    subgroup_label: str
    description: str | None = None
    share_of_diagnosed: float
    eligible_factor: float
    uptake_multiplier: float
    confidence_tier: str
    source: str
    currency: str
    by_year: list[float]
    cumulative: float
    peak_year: int
    addressable_final_year: float
    patients_treated_final_year: float
    net_cost_per_switch: float
    total_events_avoided: float
    total_cost_avoided: float
    responders_final_year: float | None = None


class SubgroupOption(BaseModel):
    """A selectable segment, before any run has happened."""

    subgroup_code: str
    subgroup_label: str
    description: str | None
    share_of_diagnosed: float
    eligible_factor: float
    uptake_multiplier: float
    confidence_tier: str
    source: str
    event_classes: list[str] = Field(default_factory=list)
    #: True when this subgroup shares patients with its siblings, so only one
    #: may be modelled at a time. The interface uses this to offer a single
    #: choice rather than a multi-select it would then have to refuse.
    is_overlapping: bool = False


# --------------------------------------------------------------------------- epidemiology


class HealthIndicatorRead(BaseModel):
    """One published burden figure, with the unit it is actually in.

    `kind` is the field that matters and it is never inferred from the name.
    A **prevalence** is the share of a population that has a condition right
    now; an **incidence** is the share that newly acquires it each year. They
    differ by more than an order of magnitude for a persistent condition like
    obesity, and reading one as the other is the single commonest error in an
    epidemiology dashboard — so the contract carries the distinction rather
    than leaving it to a label.
    """

    country_code: str
    indicator: str
    #: prevalence | incidence | coverage | policy
    kind: str
    label: str
    #: A fraction, or None for a categorical indicator.
    value: float | None
    #: The same figure per 100,000 population, which is how an incidence is
    #: conventionally quoted and read. None for a non-rate indicator.
    per_100k: float | None = None
    source: str
    source_url: str | None = None
    vintage_year: int | None = None
    confidence_tier: str


class FunnelStepRead(BaseModel):
    """One step of the population funnel, with the arithmetic that produced it.

    `working` is the step written out — "10,000,000 x 2.5%" — because a funnel
    that only shows its outputs cannot be checked. The whole reason a budget
    impact model shows a funnel at all is to answer "where did the patient
    number come from", and that question is answered by the multiplication, not
    by the result.
    """

    stage: str
    label: str
    #: What this step is, for the hover text.
    definition: str
    value: float
    #: The multiplier applied to the step above. None for the first step.
    factor: float | None = None
    factor_label: str | None = None
    working: str | None = None
    provenance: ProvenanceRead | None = None


class EpidemiologyRead(BaseModel):
    """The epidemiology block for one market — prevalence and incidence apart.

    Deliberately not one "burden" number. A payer sizing a launch needs the
    standing pool (who could start therapy at all) and the annual inflow (how
    fast that pool refills) as separate figures, because they drive different
    halves of a multi-year budget.
    """

    country_code: str
    country_name: str
    population_total: float
    adult_population: float
    #: Share of adults with the condition now.
    prevalence: float
    prevalent_cases: float
    prevalence_low: float | None = None
    prevalence_high: float | None = None
    #: Share of at-risk adults acquiring it each year.
    incidence_annual: float | None = None
    incidence_per_100k: float | None = None
    incident_cases_per_year: float | None = None
    diagnosed_cases: float
    eligible_cases: float
    treated_cases: float
    funnel: list[FunnelStepRead] = Field(default_factory=list)
    indicators: list[HealthIndicatorRead] = Field(default_factory=list)


class TotalsRead(BaseModel):
    by_year: list[float]
    cumulative: float
    peak_year: int
    currency: str


class CalculationResponse(BaseModel):
    scenario_id: uuid.UUID
    run_id: uuid.UUID | None = None
    engine_version: str
    reporting_currency: str
    fx_snapshot_date: date
    launch_year: int
    horizon_years: int
    countries: list[CountryRead]
    totals: TotalsRead
    #: M18. Empty when the run covers the whole diagnosed population as one
    #: segment, which is what every run did before subgroups existed.
    subgroups: list[SubgroupResultRead] = Field(default_factory=list)
    #: M17. The scenario's perspective, applied across every market and
    #: reported in the reporting currency.
    payer: PayerViewRead | None = None
    perspective: str | None = None
    warnings: list[WarningRead] = Field(default_factory=list)
    duration_ms: int | None = None


# --------------------------------------------------------------------------- sensitivity


class OwsaEntryRead(BaseModel):
    parameter_path: str
    label: str
    base_value: float
    low_value: float
    high_value: float
    result_at_low: float
    result_at_high: float
    swing: float
    rank: int


class OwsaResponse(BaseModel):
    scenario_id: uuid.UUID
    base_result: float
    currency: str
    entries: list[OwsaEntryRead]
    warnings: list[WarningRead] = Field(default_factory=list)


class EvidenceGapRead(BaseModel):
    parameter_path: str
    label: str
    swing: float
    influence: float
    confidence_tier: str
    weakness: float
    priority_score: float
    priority: str
    source: str
    has_provenance: bool


class EvidenceGapResponse(BaseModel):
    """M15. What to go and find out, ranked.

    Sensitivity says what moves the answer; tiers say what is weakly founded.
    Only the product says what is worth acquiring evidence for.
    """

    scenario_id: uuid.UUID
    currency: str
    max_swing: float
    gaps: list[EvidenceGapRead]


class PsaResponse(BaseModel):
    scenario_id: uuid.UUID
    currency: str
    iterations: int
    seed: int
    mean: float
    median: float
    p2_5: float
    p97_5: float
    #: Bucketed for the histogram. The raw sample vector is thousands of
    #: floats and the interface only ever draws it binned — sending both
    #: would triple the payload for no visible gain.
    histogram: list[int]
    histogram_min: float
    histogram_max: float
    exceedance: dict[str, float]
    converged: bool
    warnings: list[WarningRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- solver


class SolveRequest(BaseModel):
    target_ratio: float = Field(gt=0, lt=1)
    country_code: str | None = None


class CorridorEntryRead(BaseModel):
    country_code: str
    max_unit_price_usd: float | None
    max_annual_acquisition_usd: float | None
    feasible: bool
    unbounded: bool
    method: str
    iterations: int | None = None
    shortfall_usd: float | None = None


class SolveResponse(BaseModel):
    """The reverse solve — M8's more useful direction.

    `binding_market` is the one that sets the ceiling: the corridor is only
    as wide as its narrowest market, so that is the market a single global
    price has to satisfy.
    """

    scenario_id: uuid.UUID
    target_ratio: float
    entries: list[CorridorEntryRead]
    binding_market: str | None
    single_global_price_ceiling_usd: float | None
    warnings: list[WarningRead] = Field(default_factory=list)


class RunRead(BaseModel):
    run_id: uuid.UUID
    scenario_id: uuid.UUID
    engine_version: str
    run_type: str
    duration_ms: int | None
    created_at: datetime


class RunDetail(RunRead):
    """The full stored snapshot. `input_snapshot` is what makes a run
    reproducible: replaying it through the recorded engine version must
    give back `results` exactly."""

    input_snapshot: dict[str, Any]
    fx_snapshot: dict[str, Any]
    results: dict[str, Any]


class ScenarioDiffEntry(BaseModel):
    parameter_path: str
    country_code: str | None
    values: dict[str, float | str | bool | None]
    resolution_levels: dict[str, str]


class CompareRequest(BaseModel):
    scenario_ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


class CompareResponse(BaseModel):
    scenario_ids: list[uuid.UUID]
    indication_id: int
    reporting_currency: str
    results: list[CalculationResponse]
    diff: list[ScenarioDiffEntry]


# --------------------------------------------------------------------------- reference


class CountryOption(BaseModel):
    country_code: str
    country_name: str
    currency_code: str
    region: str | None = None
    adult_share: float | None = None


class IndicationOption(BaseModel):
    indication_id: int
    indication_name: str
    therapy_area: str


class DrugOption(BaseModel):
    drug_id: int
    drug_name: str
    generic_name: str | None
    company: str | None
    drug_class: str | None
    is_comparator: bool


# --------------------------------------------------------------------------- narrative


class CitationRead(BaseModel):
    issuing_body: str
    document_title: str
    page_number: int | None
    similarity: float
    excerpt: str


class AssumptionRead(BaseModel):
    parameter_path: str
    country_code: str | None
    value: float
    confidence_tier: str
    source: str


class NarrativeResponse(BaseModel):
    """`generated_by` names the path that produced the prose — the
    deterministic composer, or a model draft that passed numeric validation.
    The reader is entitled to know which."""

    scenario_id: uuid.UUID
    sections: dict[str, str]
    limitations: list[str]
    citations: list[CitationRead]
    assumptions: list[AssumptionRead]
    generated_by: str
    warnings: list[str] = Field(default_factory=list)
    reporting_currency: str
    cumulative: float
