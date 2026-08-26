"""Population Funnel Engine — ARCHITECTURE.md section 5.2, module M2.

Derives the addressable patient population for one market and one
launch-relative year through an ordered, auditable sequence of stages. The
funnel is the canonical structure of the system; its intermediate stages are
what make the estimate defensible.
"""

from __future__ import annotations

from .constants import PREVALENCE_MAX, PREVALENCE_MIN, FunnelStage
from .exceptions import FunnelInvariantError, UnresolvedParameterError
from .models import CountryInput, FunnelResult, FunnelStageResult, Valued


def project_population(population_total: Valued, population_growth: Valued, year: int) -> float:
    """`population_total x (1 + population_growth)^(year - 1)`.

    Factored out of `compute_funnel` because M8 needs the same projected
    population as its affordability denominator's `Pop(c,y)` — "the projected
    population from M2's first funnel stage — not the raw seeded value" (M8
    section 5.1) — without re-deriving the whole funnel to get it.
    """
    if year < 1:
        raise ValueError(f"year must be >= 1, got {year}")
    return population_total.value * (1 + population_growth.value) ** (year - 1)


def compute_funnel(country: CountryInput, criteria_factor: Valued, year: int) -> FunnelResult:
    """Stage-by-stage addressable population for one market and year.

        Pop(c,y)         = population_total(c) x (1 + pop_growth(c))^(y-1)
        Adult(c,y)       = Pop(c,y) x adult_share(c)
        Diseased(c,y)    = Adult(c,y) x prevalence(c, indication)
        Diagnosed(c,y)   = Diseased(c,y) x diagnosis_rate(c)
        Treated(c,y)     = Diagnosed(c,y) x treatment_rate(c)
        Eligible(c,y)    = Treated(c,y) x criteria_factor        <- from M3
        Addressable(c,y) = Eligible(c,y) x access_rate(c)

    `year` is launch-relative and 1-indexed; year 1 applies growth exponent 0
    (population growth is folded into the `total_population` stage's value,
    not modelled as a separate stage).

    Args:
        country: fully-resolved market input.
        criteria_factor: M3's combined eligibility factor, applied at the
            label_eligible stage.
        year: launch-relative year, 1-indexed.

    Returns:
        The seven-stage funnel, each stage carrying the factor that produced
        it and that factor's provenance (the first stage's factor is `None`).

    Raises:
        ValueError: `year < 1`, prevalence outside (0, 1) exclusive, or
            `criteria_factor` negative.
        UnresolvedParameterError: `country.adult_share` is unresolved — this
            must never silently default to 1.0 (section 5.1).
        FunnelInvariantError: a stage exceeds its predecessor. `country.funnel`
            and `Criterion.factor` are validated to (0, 1] at construction, so
            in practice this fires only for `criteria_factor` > 1 — M3's
            already-combined factor, passed in unvalidated because it isn't
            wrapped in a `Criterion`. Section 5's own words: "monotonicity can
            only fail if a factor exceeds 1," so this is that check's job, not
            a second upfront rejection here.
    """
    if year < 1:
        raise ValueError(f"year must be >= 1, got {year}")

    if not (PREVALENCE_MIN < country.prevalence.value < PREVALENCE_MAX):
        raise ValueError(
            f"prevalence must be a fraction in (0, 1) exclusive, got "
            f"{country.prevalence.value!r} (a percentage like 20.64 where 0.2064 "
            "was meant is the usual cause)"
        )

    if country.adult_share is None:
        raise UnresolvedParameterError(
            "adult_share is unresolved for this market; it must never "
            "default to 1.0",
            country_code=country.country_code,
        )

    if criteria_factor.value < 0:
        raise ValueError(f"criteria_factor must not be negative, got {criteria_factor.value!r}")

    total_population = project_population(country.population_total, country.population_growth, year)

    stages: list[FunnelStageResult] = [
        FunnelStageResult(
            stage=FunnelStage.TOTAL_POPULATION,
            value=total_population,
            factor=None,
            provenance=country.population_total.provenance,
        ),
    ]

    def _apply(stage: FunnelStage, factor: Valued) -> None:
        predecessor = stages[-1].value
        value = predecessor * factor.value
        if value > predecessor:
            raise FunnelInvariantError(
                f"{stage.value} ({value}) exceeds its predecessor ({predecessor}) "
                "— a factor > 1 was applied upstream",
                stage=stage.value, value=value, predecessor=predecessor,
            )
        stages.append(
            FunnelStageResult(
                stage=stage, value=value, factor=factor.value,
                provenance=factor.provenance,
            )
        )

    _apply(FunnelStage.ADULT_POPULATION, country.adult_share)
    _apply(FunnelStage.DISEASED, country.prevalence)
    _apply(FunnelStage.DIAGNOSED, country.funnel.diagnosis_rate)
    _apply(FunnelStage.TREATED, country.funnel.treatment_rate)
    _apply(FunnelStage.LABEL_ELIGIBLE, criteria_factor)
    _apply(FunnelStage.ADDRESSABLE, country.funnel.access_rate)

    return FunnelResult(country_code=country.country_code, year=year, stages=tuple(stages))
