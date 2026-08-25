"""Comparator discovery endpoints — M11 section 8."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..constants.comparator import CompetitorClass
from ..dal import get_session
from ..schemas.comparator import AssetIntake, PromotionRequest, RegisteredAsset
from ..services.comparator_registry_service import ComparatorRegistryService
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


# --------------------------------------------------------------------------- registry (M12)


@router.get("/assets")
def list_assets(
    session: SessionDep,
    indication_id: int,
    competitor_class: CompetitorClass | None = None,
) -> list[RegisteredAsset]:
    """The registry for one indication, most relevant first."""
    return ComparatorRegistryService(session).list_assets(
        indication_id,
        competitor_class=competitor_class.value if competitor_class else None,
    )


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def register_asset(
    session: SessionDep, intake: AssetIntake, response: Response,
) -> RegisteredAsset:
    """Register a new asset or a discovered comparator.

    Idempotent on `(source_id, indication_id)`: running discovery twice and
    registering the same molecule twice is ordinary, not a conflict.
    """
    asset = ComparatorRegistryService(session).register(intake)
    session.commit()
    response.headers["Location"] = f"/api/v1/comparators/assets/{asset.asset_id}"
    return asset


@router.get("/assets/{asset_id}")
def read_asset(session: SessionDep, asset_id: int) -> RegisteredAsset:
    return ComparatorRegistryService(session).read(asset_id)


@router.post("/assets/{asset_id}/promote")
def promote_asset(
    session: SessionDep, asset_id: int, request: PromotionRequest,
) -> RegisteredAsset:
    """Attach a regimen and prices, making the asset usable by M5.

    All of it or none: the service raises before anything is written if a
    market or currency does not check out, and the session is only committed
    once every row is in place.
    """
    asset = ComparatorRegistryService(session).promote(asset_id, request)
    session.commit()
    return asset
