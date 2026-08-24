"""Narrative and export endpoints — M10 section 8.

The exit criterion for the project lives here: a complete scenario produces
a distributable, fully cited deliverable.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..dal import get_session
from ..schemas.calculation import AssumptionRead, CitationRead, NarrativeResponse
from ..services.calculation_service import CalculationService
from ..services.export_service import build_pdf, build_pptx
from ..services.narrative_service import NarrativeService
from ..services.scenario_service import ScenarioService

router = APIRouter(prefix="/api/v1", tags=["evidence"])

SessionDep = Annotated[Session, Depends(get_session)]

PDF_MEDIA = "application/pdf"
PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _safe_filename(name: str, extension: str) -> str:
    """A filename a browser will accept from an asset name typed by a user.

    Anything outside a conservative set becomes an underscore — an asset
    called `Wegovy 2.4mg (EU/US)` must not produce a header the browser
    truncates at the slash.
    """
    cleaned = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip()
    return f"{(cleaned or 'budget-impact').replace(' ', '-')}.{extension}"


def _build(session: Session, scenario_id: uuid.UUID) -> tuple[object, object, str]:
    scenario = ScenarioService(session).require(scenario_id)
    response, engine_input, _ = CalculationService(session).calculate(scenario)
    narrative = NarrativeService(session).generate(response, engine_input)
    return response, narrative, scenario.asset_name


@router.get("/scenarios/{scenario_id}/narrative", response_model=NarrativeResponse)
def narrative(scenario_id: uuid.UUID, session: SessionDep) -> NarrativeResponse:
    """The written account, grounded in retrieved guidance.

    `generated_by` says which path produced it — the deterministic composer
    or a validated model draft. That distinction belongs to the reader, not
    just the logs.
    """
    response, narr, _ = _build(session, scenario_id)

    return NarrativeResponse(
        scenario_id=scenario_id,
        sections=narr.sections,                              # type: ignore[attr-defined]
        limitations=list(narr.limitations),                  # type: ignore[attr-defined]
        citations=[
            CitationRead(
                issuing_body=c.issuing_body,
                document_title=c.document_title,
                page_number=c.page_number,
                similarity=round(c.similarity, 3),
                excerpt=c.text[:240],
            )
            for c in narr.citations                          # type: ignore[attr-defined]
        ],
        assumptions=[
            AssumptionRead(
                parameter_path=a.parameter_path,
                country_code=a.country_code,
                value=a.value,
                confidence_tier=str(a.confidence_tier),
                source=a.source,
            )
            for a in narr.assumptions                        # type: ignore[attr-defined]
        ],
        generated_by=narr.generated_by,                      # type: ignore[attr-defined]
        warnings=list(narr.warnings),                        # type: ignore[attr-defined]
        reporting_currency=response.reporting_currency,      # type: ignore[attr-defined]
        cumulative=response.totals.cumulative,               # type: ignore[attr-defined]
    )


@router.get("/scenarios/{scenario_id}/export.pdf")
def export_pdf(scenario_id: uuid.UUID, session: SessionDep) -> Response:
    response, narr, asset = _build(session, scenario_id)
    payload = build_pdf(response, narr, asset)               # type: ignore[arg-type]
    filename = _safe_filename(asset, "pdf")
    return Response(
        content=payload,
        media_type=PDF_MEDIA,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{filename}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/scenarios/{scenario_id}/export.pptx")
def export_pptx(scenario_id: uuid.UUID, session: SessionDep) -> Response:
    response, narr, asset = _build(session, scenario_id)
    payload = build_pptx(response, narr, asset)              # type: ignore[arg-type]
    filename = _safe_filename(asset, "pptx")
    return Response(
        content=payload,
        media_type=PPTX_MEDIA,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{filename}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )
