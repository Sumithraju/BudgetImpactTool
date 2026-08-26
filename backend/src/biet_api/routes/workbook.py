"""Workbook templates and import — M19.

Templates go out pre-filled with the model's own current figures, so the
analyst is asked to correct what they disagree with rather than to reproduce
from nothing what the model already knows.

Import returns a *draft*, never a saved scenario. The caller reviews what the
file was read as, then creates the scenario through the ordinary endpoint —
which means an imported scenario goes through exactly the same validation as a
typed one, rather than through a second, more forgiving path.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..constants.field_guide import FIELD_GROUPS
from ..dal import get_session
from ..exceptions import ValidationError
from ..schemas.pricing import ImportResponse
from ..services.pricing_service import PricingService
from ..services.workbook_service import WorkbookService

router = APIRouter(prefix="/api/v1/workbook", tags=["workbook"])

SessionDep = Annotated[Session, Depends(get_session)]

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

#: Refused above this. An import is parsed entirely in memory, and the largest
#: legitimate scenario workbook here is a few hundred rows — anything at this
#: size is a mistake or an attack, and either way the useful response is a
#: clear refusal rather than an exhausted process.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@router.get("/field-guide")
def field_guide() -> list[dict[str, object]]:
    """What every input means, grouped and ordered as the model computes.

    Served rather than duplicated in the interface, for the same reason the
    affordability bands are: one description of a field, used by the hover
    text, the import template, the exported workbook and the assumption
    register alike. Four copies of a sentence is four chances to disagree.
    """
    return [
        {
            "key": group.key,
            "label": group.label,
            "summary": group.summary,
            "fields": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "description": spec.description,
                    "effect": spec.effect,
                    "unit": spec.unit,
                    "parameter_path": spec.parameter_path,
                    "example": spec.example,
                    "typical_range": spec.typical_range,
                }
                for spec in group.fields
            ],
        }
        for group in FIELD_GROUPS
    ]


@router.get("/template.xlsx")
def scenario_template(
    session: SessionDep,
    indication_id: int = 1,
    country_codes: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """The scenario workbook, pre-filled with the current price grid."""
    prices = (
        PricingService(session).grid(indication_id, country_codes)
        if country_codes else []
    )
    payload = WorkbookService().scenario_template(prices)
    return Response(
        content=payload,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="biet-scenario-template.xlsx"'
        },
    )


@router.get("/template.csv")
def scenario_template_csv() -> Response:
    """The same fields, flattened, for anyone not working in Excel."""
    return Response(
        content=WorkbookService().scenario_template_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="biet-scenario-template.csv"'
        },
    )


@router.get("/prices.csv")
def price_template_csv(
    session: SessionDep,
    indication_id: int,
    country_codes: Annotated[list[str], Query()],
) -> Response:
    """The price grid as a CSV, every cell editable.

    Includes the markets with no observed price, carrying the derivation the
    engine would use. Those are the rows worth an analyst's attention first,
    and an empty cell would hide them rather than surface them.
    """
    prices = PricingService(session).grid(indication_id, country_codes)
    return Response(
        content=WorkbookService().price_template_csv(prices),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="biet-comparator-prices.csv"'
        },
    )


@router.post("/import", response_model=ImportResponse)
async def import_workbook(
    file: Annotated[UploadFile, File()],
) -> ImportResponse:
    """Parse a filled-in workbook or CSV into a scenario draft.

    Nothing is saved. The response carries what the file was read as and every
    cell that was refused, with its sheet and row — the caller shows both, and
    creates the scenario through the ordinary endpoint once the analyst has
    agreed with the reading.
    """
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"That file is {len(payload) / 1_048_576:.1f} MB. The importer "
            f"accepts up to {MAX_UPLOAD_BYTES // 1_048_576} MB — a scenario "
            "workbook is a few hundred rows, so a file this size is usually "
            "the wrong one.",
            field="file",
        )
    if not payload:
        raise ValidationError("That file is empty.", field="file")

    name = file.filename or "upload.xlsx"
    if not name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise ValidationError(
            f"{name!r} is not a workbook or a CSV. Download the template, fill "
            "in the Value column and send that back.",
            field="file",
        )
    return WorkbookService().parse(payload, name)
