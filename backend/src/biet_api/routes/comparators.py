"""Comparator discovery endpoints — M11 section 8."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..constants.comparator import CompetitorClass
from ..constants.workbook import WorkbookColumn
from ..dal import get_session
from ..repositories.reference import ReferenceRepository
from ..schemas.comparator import AssetIntake, PromotionRequest, RegisteredAsset
from ..schemas.comparator_import import ComparatorImportResult
from ..services.comparator_import_service import ComparatorImportService
from ..services.comparator_registry_service import ComparatorRegistryService
from ..services.comparator_service import ComparatorService
from ..services.landscape_service import LandscapeService
from ..services.safety_service import SafetyService

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


# --------------------------------------------------------------------------- safety (M13)


@router.get("/safety")
def safety_comparison(
    session: SessionDep,
    country_code: Annotated[str, Query(min_length=3, max_length=3)],
    drug_ids: Annotated[list[int], Query()],
) -> dict[str, Any]:
    """Per-event incidences for a set of therapies, with their sources.

    The bridge gives one adverse-event number per therapy; this is what that
    number was computed from, so a reader can check it rather than take it.
    """
    return SafetyService(session).comparison(drug_ids, country_code)


# --------------------------------------------------------------------------- landscape (M14)


@router.get("/landscape")
def landscape(
    session: SessionDep,
    indication_id: int,
    launch_year: Annotated[int, Query(ge=2000, le=2100)],
    horizon_years: Annotated[int, Query(ge=1, le=5)] = 3,
) -> dict[str, Any]:
    """The market an asset launching in `launch_year` would actually meet.

    Reports which registered pipeline entrants are modellable and which are
    not, with the reason for each — an entrant left out because nobody has
    stated a plateau share is a different situation from one left out because
    it arrives after the horizon ends.
    """
    return LandscapeService(session).preview(
        indication_id, launch_year=launch_year, horizon_years=horizon_years,
    )


@router.get("/import/template")
def import_template() -> Response:
    """The empty comparator file, headers in place.

    Offered before the upload control, because the first question an analyst
    has is what shape the file should be (M19 section 9).
    """
    header = ",".join(column.value for column in WorkbookColumn)
    example = "Ozempic,Standard of care,DEU,EUR,40,1200,0,150,60,EMA list price,B"
    body = f"{header}\n{example}\n"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="comparators-template.csv"'},
    )


@router.post("/import")
async def import_comparators(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> ComparatorImportResult:
    """Validate an uploaded comparator sheet — M19 sections 5.1 to 5.4.

    Validation only: nothing is written. An accepted result carries the parsed
    rows for review, and a row reaches the registry through M12's promotion
    path, which requires a regimen and a priced source. Letting a spreadsheet
    write to the registry directly would make it two records of what a drug is
    rather than one (M19 section 5.6).
    """
    reference = ReferenceRepository(session)
    rates, _ = reference.load_fx_snapshot()
    service = ComparatorImportService(
        known_markets=frozenset(reference.list_active_country_codes()),
        known_currencies=frozenset(rates),
    )
    return service.parse(await file.read(), file.filename or "upload")
