"""Reference-data endpoints — what the interface needs to build its pickers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from biet_engine.constants import DISJOINT_SUBGROUPS, SUBGROUP_PRIORITY, Subgroup

from ..constants.subgroups import (
    DEFAULT_SUBGROUP_SHARES,
    SUBGROUP_DEFINITIONS,
    SUBGROUP_LABELS,
    SUBGROUP_SHARE_SOURCE,
    SUBGROUP_SHARE_TIER,
)
from ..dal import get_session
from ..models.reference import Country, Drug, Indication
from ..schemas.calculation import (
    CountryOption,
    DrugOption,
    IndicationOption,
    SubgroupOption,
)

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
def list_subgroups() -> list[SubgroupOption]:
    """The obesity subgroup taxonomy and its seeded shares — M18 section 8.

    Shares are the fraction of the adult obesity population whose highest
    priority qualifying condition is that one, so the four supplied ones sum to
    less than 1 and obesity alone is the residual. Every share is tier C and
    global rather than country-specific; the payload says so rather than
    leaving a reader to assume otherwise.
    """
    return [
        SubgroupOption(
            code=subgroup.value,
            label=SUBGROUP_LABELS[subgroup],
            definition=SUBGROUP_DEFINITIONS[subgroup],
            default_share=DEFAULT_SUBGROUP_SHARES.get(subgroup),
            is_residual=subgroup is Subgroup.OBESITY_ALONE,
            is_disjoint=subgroup in DISJOINT_SUBGROUPS,
            source=SUBGROUP_SHARE_SOURCE,
            confidence_tier=SUBGROUP_SHARE_TIER,
        )
        for subgroup in (*SUBGROUP_PRIORITY, Subgroup.PAEDIATRIC_OBESITY)
    ]
