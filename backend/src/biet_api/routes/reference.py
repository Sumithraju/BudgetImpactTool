"""Reference-data endpoints — what the interface needs to build its pickers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants.domain import SUBSET_PERSPECTIVES, Perspective
from ..dal import get_session
from ..models.reference import Country, Drug, Indication
from ..repositories.outcomes import OutcomesRepository
from ..repositories.reference import ReferenceRepository
from ..schemas.calculation import (
    CountryOption,
    CriterionOption,
    DrugOption,
    HealthIndicatorRead,
    IndicationOption,
    SubgroupOption,
)
from ..schemas.pricing import DrugPriceRead, PerspectiveOption
from ..services.outcomes_service import OutcomesService
from ..services.payer_service import PERSPECTIVE_LABELS
from ..services.pricing_service import PricingService

#: What each perspective actually changes about the reading, in one line.
#: Beside the labels rather than in the interface, so the deck, the PDF and
#: the screen all describe a perspective the same way.
PERSPECTIVE_DESCRIPTIONS: dict[str, str] = {
    Perspective.INSURER: (
        "A commercial plan. Reads per-member-per-month against its own covered "
        "lives, and counts only the costs it reimburses."
    ),
    Perspective.EMPLOYER: (
        "A self-insured employer. The smallest denominator of the four, so the "
        "same national impact reads as a far larger per-member figure."
    ),
    Perspective.GOVERNMENT: (
        "A national or regional public payer. Reads against the covered "
        "population it is responsible for, at the prices it actually pays."
    ),
    Perspective.HEALTH_SYSTEM: (
        "The whole system. The denominator is the national population, so no "
        "covered-lives figure is needed — this is the default every run used "
        "before perspectives existed."
    ),
}

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/countries", response_model=list[CountryOption])
def list_countries(session: SessionDep) -> list[CountryOption]:
    rows = session.scalars(
        select(Country).where(Country.is_active.is_(True)).order_by(Country.country_code)
    ).all()
    return [
        CountryOption(
            country_code=r.country_code, country_name=r.country_name,
            currency_code=r.currency_code, region=r.region,
            adult_share=float(r.adult_share) if r.adult_share is not None else None,
        )
        for r in rows
    ]


@router.get("/indications", response_model=list[IndicationOption])
def list_indications(session: SessionDep) -> list[IndicationOption]:
    rows = session.scalars(
        select(Indication).order_by(Indication.indication_id)
    ).all()
    return [
        IndicationOption(
            indication_id=r.indication_id, indication_name=r.indication_name,
            therapy_area=r.therapy_area,
        )
        for r in rows
    ]


@router.get("/drugs", response_model=list[DrugOption])
def list_drugs(session: SessionDep, indication_id: int | None = None) -> list[DrugOption]:
    stmt = select(Drug).order_by(Drug.drug_id)
    if indication_id is not None:
        stmt = stmt.where(Drug.indication_id == indication_id)
    rows = session.scalars(stmt).all()
    return [
        DrugOption(
            drug_id=r.drug_id, drug_name=r.drug_name, generic_name=r.generic_name,
            company=r.company, drug_class=r.drug_class, is_comparator=r.is_comparator,
        )
        for r in rows
    ]


@router.get("/parameter-paths", response_model=list[str])
def list_parameter_paths() -> list[str]:
    """The closed override vocabulary, so the interface can offer exactly the
    paths the validator will accept rather than duplicating the list."""
    from ..constants.parameter_paths import VALID_PATH_TEMPLATES

    return list(VALID_PATH_TEMPLATES)


@router.get("/affordability-bands", response_model=dict[str, float])
def affordability_bands() -> dict[str, float]:
    """The band boundaries, as fractions of national health expenditure.

    Served rather than duplicated in the interface: a threshold that drifts
    between the engine and the gauge drawing it would mislabel a result
    without either side erroring.
    """
    from biet_engine.constants import AFFORDABILITY_THRESHOLDS

    return {band.value: threshold for band, threshold in AFFORDABILITY_THRESHOLDS.items()}


@router.get("/subgroups", response_model=list[SubgroupOption])
def list_subgroups(session: SessionDep, indication_id: int) -> list[SubgroupOption]:
    """M18. The clinically distinct populations inside one disease.

    Served before any run so the interface can offer the segmentation as a
    choice rather than as a result. Each option carries its share, its source
    and its confidence tier, because a reader selecting segments is choosing
    between assumptions and is entitled to see which.
    """
    service = OutcomesService(session)
    return [
        SubgroupOption(
            subgroup_code=s.subgroup_code,
            subgroup_label=s.subgroup_label,
            description=s.description,
            share_of_diagnosed=float(s.share_of_diagnosed),
            eligible_factor=float(s.eligible_factor),
            uptake_multiplier=float(s.uptake_multiplier),
            confidence_tier=str(s.confidence_tier),
            source=s.source,
            event_classes=sorted(r.event_class for r in s.event_rates),
            is_overlapping=s.is_overlapping,
        )
        for s in service.list_subgroups(indication_id)
        # The whole-population row is the denominator the others are shares of,
        # not a restriction anyone chooses. It is what a run models when nothing
        # is selected, so offering it as an option would be offering the default
        # twice.
        if not s.is_default_population
    ]


@router.get("/criteria", response_model=list[CriterionOption])
def list_criteria(session: SessionDep, indication_id: int) -> list[CriterionOption]:
    """M3. The eligibility restrictions that narrow the diagnosed population.

    Served before any run for the same reason the subgroups are: each factor
    is an assumption the reader is entitled to see and to move, and a funnel
    that only reveals them after a calculation makes them look like findings
    rather than inputs.

    `enabled` mirrors the stack `EngineInputBuilder._build_criteria` would
    construct for a run with no overrides — a criterion is skipped when it is
    correlated with one already enabled, so that two clinically overlapping
    restrictions are never compounded. Recomputed here rather than imported so
    this endpoint stays a read of reference data; the rule is small and the
    duplication is covered by a test that pins the two together.
    """
    rows = ReferenceRepository(session).list_criteria(indication_id)

    enabled_codes: set[str] = set()
    correlated_with_enabled: set[str] = set()
    out: list[CriterionOption] = []
    for row in rows:
        correlations = tuple(row.correlated_with or ())
        enabled = row.criterion_code not in correlated_with_enabled
        if enabled:
            enabled_codes.add(row.criterion_code)
            correlated_with_enabled.update(correlations)
        out.append(
            CriterionOption(
                criterion_code=row.criterion_code,
                criterion_label=row.criterion_label,
                criterion_type=str(row.criterion_type),
                default_factor=float(row.default_factor),
                factor_low=float(row.factor_low) if row.factor_low is not None else None,
                factor_high=(
                    float(row.factor_high) if row.factor_high is not None else None
                ),
                enabled=enabled,
                correlated_with=list(correlations),
                confidence_tier=str(row.confidence_tier),
                source=row.source,
            )
        )
    return out


@router.get("/perspectives", response_model=list[PerspectiveOption])
def list_perspectives() -> list[PerspectiveOption]:
    """M17. Whose budget the impact lands on.

    `requires_covered_population` is the field that matters. An insurer or an
    employer covers a subset of the nation, and a per-member figure computed
    against the national population is wrong by the ratio between them — so the
    interface has to know which perspectives need the number before the user
    picks one, not after.
    """
    return [
        PerspectiveOption(
            code=member.value,
            label=PERSPECTIVE_LABELS[member.value],
            description=PERSPECTIVE_DESCRIPTIONS[member.value],
            requires_covered_population=member in SUBSET_PERSPECTIVES,
        )
        for member in Perspective
    ]


@router.get("/prices", response_model=list[DrugPriceRead])
def list_prices(
    session: SessionDep, indication_id: int, country_codes: Annotated[list[str], Query()],
) -> list[DrugPriceRead]:
    """Every therapy's price in every requested market, observed or derived.

    The interface needs the *whole* grid, including the cells with no observed
    price, because those are exactly the ones an analyst wants to fill in. A
    row with `is_observed=False` carries the purchasing-power derivation the
    engine would use, so the field can be pre-filled with the model's own
    working assumption rather than left blank.
    """
    return PricingService(session).grid(indication_id, country_codes)


@router.get("/epidemiology", response_model=list[HealthIndicatorRead])
def market_epidemiology(
    session: SessionDep, country_codes: Annotated[list[str], Query()],
) -> list[HealthIndicatorRead]:
    """WHO's published burden figures for a set of markets, before any run.

    Served separately from the calculation so the build screen can show what a
    scenario rests on *while it is being defined*, rather than only after it has
    been computed. An analyst choosing markets is making an epidemiological
    decision, and the figures that decision turns on should be on the same
    screen as the choice.
    """
    rows = OutcomesRepository(session).health_indicators(country_codes)
    return [
        HealthIndicatorRead(
            country_code=code,
            indicator=indicator,
            kind=row.indicator_kind,
            label=row.label,
            value=None if row.value is None else float(row.value),
            per_100k=(
                float(row.value) * 100_000
                if row.value is not None
                and row.indicator_kind in {"prevalence", "incidence"}
                else None
            ),
            source=row.source,
            source_url=row.source_url,
            vintage_year=row.vintage_year,
            confidence_tier=str(row.confidence_tier),
        )
        for (code, indicator), row in sorted(rows.items())
    ]
