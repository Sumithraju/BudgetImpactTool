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


class Perspective(StrEnum):
    """Whose budget the impact lands on — M17 section 5.1.

    Not a cosmetic label. The perspective selects the denominator (an insurer
    covering four million lives and a national health system are not reading
    the same per-member figure) and decides whether indirect costs are in
    scope at all. A number quoted without one is unreadable: "$40 million"
    means something different to each of these four readers.
    """

    INSURER = "insurer"
    EMPLOYER = "employer"
    GOVERNMENT = "government"
    HEALTH_SYSTEM = "health_system"


#: Perspectives whose covered population is a *subset* of the national one and
#: must therefore be supplied. A health system's denominator is the national
#: population, which the funnel already resolves.
SUBSET_PERSPECTIVES: Final[frozenset[Perspective]] = frozenset(
    {Perspective.INSURER, Perspective.EMPLOYER}
)


class UptakeScenario(StrEnum):
    """The three adoption cases a payer conversation is held in — M17 §5.5."""

    LOW = "low"
    BASE = "base"
    HIGH = "high"


#: Multipliers on the scenario's terminal uptake for the low and high cases.
#: Symmetric around the base case and stated rather than derived: no source
#: supplies an adoption interval for an unlaunched asset, so this is a framing
#: device for the conversation, not an estimate of uncertainty. M9's PSA is
#: where genuine uncertainty is quantified.
UPTAKE_SCENARIO_MULTIPLIER: Final[dict[UptakeScenario, float]] = {
    UptakeScenario.LOW: 0.5,
    UptakeScenario.BASE: 1.0,
    UptakeScenario.HIGH: 1.75,
}


class EventClass(StrEnum):
    """Clinical events a therapy can avoid — M16 section 4.

    Mirrored from `biet_engine.constants`; `test_constants_parity.py` guards
    the two from drifting.
    """

    INCIDENT_T2D = "incident_t2d"
    MACE = "mace"
    HOSPITALISATION = "hospitalisation"
    OSA_PROGRESSION = "osa_progression"
    HYPERTENSION = "hypertension"


class ResponseThreshold(StrEnum):
    """Weight-loss thresholds trials report responder proportions against."""

    WL_5 = "wl_5"
    WL_10 = "wl_10"
    WL_15 = "wl_15"


#: Reader-facing names for the closed sets above. Kept beside the enums rather
#: than in the frontend so one vocabulary serves the interface, the PDF, the
#: deck and the workbook — a label that differs between the screen and the
#: export is a defect a reader has no way to resolve.
EVENT_LABELS: Final[dict[str, str]] = {
    EventClass.INCIDENT_T2D: "New cases of type 2 diabetes",
    EventClass.MACE: "Major cardiovascular events",
    EventClass.HOSPITALISATION: "Hospital admissions",
    EventClass.OSA_PROGRESSION: "Sleep-apnoea progression",
    EventClass.HYPERTENSION: "New cases of hypertension",
}

RESPONSE_THRESHOLD_LABELS: Final[dict[str, str]] = {
    ResponseThreshold.WL_5: "at least 5% weight loss",
    ResponseThreshold.WL_10: "at least 10% weight loss",
    ResponseThreshold.WL_15: "at least 15% weight loss",
}


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
    # M18. The seeded subgroup shares do not partition the diagnosed
    # population. Segments that overlap double-count patients; segments that
    # under-cover silently drop them.
    SUBGROUP_SHARES_UNBALANCED = "SUBGROUP_SHARES_UNBALANCED"
    # A therapy that is part of current care carries no price in any market, so
    # it cannot be costed and is excluded from the world-without. Named rather
    # than silent: its absence overstates budget impact by exactly what it
    # costs today.
    COMPARATOR_UNPRICED = "COMPARATOR_UNPRICED"
    # M16. An event has an avoided-event count but no unit cost in this
    # market, so the offset it represents is missing rather than zero.
    EVENT_COST_MISSING = "EVENT_COST_MISSING"
    # M17. A per-member figure was requested for a perspective whose covered
    # population was not supplied, so the national population stands in.
    COVERED_POPULATION_ASSUMED = "COVERED_POPULATION_ASSUMED"
    # M19. A workbook cell parsed but fell outside the range its parameter
    # accepts, or named a market the scenario does not include.
    IMPORT_CELL_REJECTED = "IMPORT_CELL_REJECTED"
