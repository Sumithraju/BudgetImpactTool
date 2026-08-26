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


class SegmentRead(BaseModel):
    """One subgroup's contribution to the scenario — M18 section 5.4."""

    code: str
    label: str
    share: float
    cumulative_impact: float
    #: Signed. Not a proportion when segments pull in opposite directions.
    share_of_total_impact: float
    addressable_final_year: float
    patients_on_new_final_year: float


class SegmentedCalculationResponse(BaseModel):
    """The scenario run once per subgroup and aggregated."""

    scenario_id: uuid.UUID
    engine_version: str
    reporting_currency: str
    launch_year: int
    horizon_years: int
    totals: TotalsRead
    segments: list[SegmentRead]
    warnings: list[WarningRead]
    duration_ms: int | None = None


class SubgroupOption(BaseModel):
    """One subgroup for the picker — M18 section 8."""

    code: str
    label: str
    definition: str
    #: None for the residual and for the disjoint paediatric segment, neither
    #: of which is supplied as part of the adult partition.
    default_share: float | None
    is_residual: bool
    is_disjoint: bool
    source: str
    confidence_tier: str


class TotalsRead(BaseModel):
    by_year: list[float]
    cumulative: float
    peak_year: int
    currency: str
    #: The world without the asset and the world with it, per year, in the
    #: reporting currency. `by_year` is their difference.
    without_by_year: list[float] = []
    with_by_year: list[float] = []


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
