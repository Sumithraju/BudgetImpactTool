"""Closed sets, as enums.

Domain vocabulary is fixed by ARCHITECTURE.md Appendix A. Use `addressable`, not
`eligible_final`; `persistence`, not `adherence`; `budget_impact`, never `cost`,
for the incremental quantity.

This module is the single definition of these sets. The ingestion package
re-exports from here rather than declaring its own.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class ConfidenceTier(StrEnum):
    """How much weight a published value carries.

    A — observed and published by the source.
    B — derived from an observed value under a stated assumption.
    C — projected, extrapolated, or estimated.
    D — placeholder; must be overridden before a result is relied on.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EconomicIndicator(StrEnum):
    """`country_economics.indicator`. World Bank series, renamed to domain terms."""

    POPULATION_TOTAL = "population_total"
    GDP_PC_PPP = "gdp_pc_ppp"
    HEALTH_EXP_PC_USD = "health_exp_pc_usd"
    OOP_HEALTH_PCT = "oop_health_pct"
    POP_0014_PCT = "pop_0014_pct"


class FunnelStage(StrEnum):
    """`funnel_defaults.stage` and the M2 funnel. Order is the funnel order."""

    TOTAL_POPULATION = "total_population"
    ADULT_POPULATION = "adult_population"
    DISEASED = "diseased"
    DIAGNOSED = "diagnosed"
    TREATED = "treated"
    LABEL_ELIGIBLE = "label_eligible"
    ADDRESSABLE = "addressable"


#: The stages a seed file may supply a rate for. The others are derived.
SEEDABLE_FUNNEL_STAGES: Final[frozenset[FunnelStage]] = frozenset(
    {FunnelStage.DIAGNOSED, FunnelStage.TREATED, FunnelStage.ADDRESSABLE}
)


class CriterionType(StrEnum):
    """`eligibility_criteria.criterion_type`."""

    BMI = "bmi"
    COMORBIDITY = "comorbidity"
    HBA1C = "hba1c"
    AGE = "age"
    LINE_OF_THERAPY = "line_of_therapy"
    PRIOR_FAILURE = "prior_failure"


class CostComponent(StrEnum):
    """The parts an annual therapy cost is built from (M5 section 5.5).

    Mirrored from `biet_engine.constants` — the engine cannot import this
    module, and `test_constants_parity.py` guards the two from drifting.
    """

    ACQUISITION = "acquisition"
    ADMIN = "admin"
    MONITORING = "monitoring"
    AE = "ae"
    OFFSET = "offset"


class PriceBasis(StrEnum):
    """`drug_prices.price_basis`.

    A row with basis `ESTIMATED_NET` must carry `gross_to_net_pct` and cite the
    assumption behind it (M0 section 5.6).
    """

    LIST = "list"
    NADAC = "nadac"
    ESTIMATED_NET = "estimated_net"
    PPP_DERIVED = "ppp_derived"


class TherapyArea(StrEnum):
    OBESITY = "obesity"
    TYPE_2_DIABETES = "type_2_diabetes"


class RunType(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"
    OWSA = "owsa"
    PSA = "psa"


class UptakeCurve(StrEnum):
    LINEAR = "linear"
    LOGISTIC = "logistic"
    MANUAL = "manual"


class AffordabilityBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class IssuingBody(StrEnum):
    """`guideline_documents.issuing_body`."""

    ISPOR = "ISPOR"
    NICE = "NICE"
    WHO = "WHO"
    CDA_AMC = "CDA-AMC"


class WarningCode(StrEnum):
    """Warnings are not errors: they travel with a result, they do not replace it."""

    STALE_VINTAGE = "STALE_VINTAGE"
    PROJECTED_VALUE = "PROJECTED_VALUE"
    MISSING_NDC_MAPPING = "MISSING_NDC_MAPPING"
    ESTIMATED_NET_PRICE = "ESTIMATED_NET_PRICE"
    # M1 section 5.3's fourth resolution warning; the engine raises the rest
    # of its own codes (SUBSTITUTION_FLOOR, CORRELATED_CRITERIA, ...) as
    # literal strings on `Warning_`, since it cannot import this module.
    TIER_D_INPUT = "TIER_D_INPUT"
    UNPRICED_MARKET = "UNPRICED_MARKET"
    # Raised when one market's therapies do not share a price basis — an
    # observed price compared against PPP-derived comparators is not a
    # like-for-like comparison, and the impact can flip sign.
    MIXED_PRICE_BASIS = "MIXED_PRICE_BASIS"
    # M13. Pricing one therapy's adverse events while leaving its comparators
    # at zero inflates that therapy's apparent cost — or, with the sides
    # reversed, manufactures a saving.
    AE_PROFILE_ASYMMETRIC = "AE_PROFILE_ASYMMETRIC"
    # M13. The unit management cost is an analyst construction rather than an
    # observed cost, or is missing for some events in this market.
    AE_COST_DERIVED = "AE_COST_DERIVED"
    # M13. No unit management cost is seeded for this market at all — the
    # events are priced at nothing, which is missing data rather than a
    # therapy that causes none.
    AE_COST_MISSING = "AE_COST_MISSING"
    # M14. The world-without includes therapies that are not yet approved.
    PIPELINE_ENTRANT_MODELLED = "PIPELINE_ENTRANT_MODELLED"
    # M14. A registered pipeline therapy was kept out of the world-without,
    # because it is not marketed and the scenario did not ask to project it.
    PIPELINE_ENTRANT_EXCLUDED = "PIPELINE_ENTRANT_EXCLUDED"
