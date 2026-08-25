"""Comparator discovery endpoints — M11 section 8."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dal import get_session
from ..services.comparator_service import ComparatorService

router = APIRouter(prefix="/api/v1/comparators", tags=["comparators"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/discover")
def discover(
    session: SessionDep,
    target: Annotated[str, Query(min_length=2, max_length=40)],
    indication_id: int,
    mechanism: str | None = None,
    include_pathway: bool = False,
) -> dict[str, Any]:
    """Marketed and late-stage therapies acting on one target.

    Returns candidates grouped and ranked; it does not write them into any
    scenario. Whether a drug is a real comparator depends on line of
    therapy, formulary position and clinical positioning, none of which the
    source databases know — so selection stays an explicit human act
    (M11 section 5.6).
    """
    return ComparatorService(session).discover(
        target, indication_id, mechanism=mechanism, include_pathway=include_pathway,
    )


@router.get("/targets/{symbol}")
def resolve_target(symbol: str) -> dict[str, Any]:
    """Resolve a gene symbol to an Ensembl id and its Reactome pathways.

    Separate from discovery because it is the cheap half: an interface can
    confirm a target exists, and show what it is, while the user is still
    typing — without paying for the candidate retrieval.
    """
    return ComparatorService.resolve(symbol)
