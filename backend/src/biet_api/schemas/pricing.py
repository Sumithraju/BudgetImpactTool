"""Price-grid and workbook contracts — M19 and the editable price table.

The price grid is the one screen where an analyst is most likely to disagree
with the model, and rightly: only three of ten markets carry an observed price
for this class, and the rest are derived through purchasing-power parity from a
US list price that sits far above European reality. A tool that presents those
derived figures as read-only is telling the analyst their own market knowledge
is inadmissible.

So every cell is editable, and the contract makes the distinction visible
rather than flattening it — `is_observed` says whether a number was found or
constructed, and an edit becomes a scenario override with its own provenance
instead of overwriting the reference data. A market's real price and one
analyst's working assumption are different claims and the database keeps them
apart.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PerspectiveOption(BaseModel):
    code: str
    label: str
    description: str
    #: Whether this perspective's denominator is a subset of the nation, and
    #: therefore has to be supplied before any per-member figure means
    #: anything.
    requires_covered_population: bool


class DrugPriceRead(BaseModel):
    """One therapy's price in one market.

    `annual_cost` is included even though it is derivable, because it is the
    figure an analyst actually recognises. A unit price of 0.4523 per unit
    means nothing on sight; €4,979 a year is immediately either right or wrong
    to someone who knows the market, and that recognition is the whole point of
    making the grid editable.
    """

    drug_id: int
    drug_name: str
    is_new_asset: bool
    country_code: str
    currency_code: str
    unit_price: float
    annual_cost: float
    price_basis: str
    #: False when the figure was derived rather than found. These are the cells
    #: worth an analyst's attention first.
    is_observed: bool
    confidence_tier: str
    source: str
    source_url: str | None = None
    vintage_year: int | None = None
    #: The override path an edit to this cell writes to, supplied so the
    #: interface never has to construct a parameter path by string
    #: concatenation — an override addressed to a path outside the closed
    #: vocabulary is silently discarded, which is the failure mode the
    #: vocabulary exists to prevent.
    parameter_path: str


class PriceEdit(BaseModel):
    """One analyst-supplied price, as it arrives from the grid or a workbook."""

    drug_id: int
    country_code: str
    unit_price: float | None = Field(default=None, gt=0)
    #: Either end may be supplied. An analyst reading a market knows the annual
    #: cost; the engine needs the unit price. Whichever arrives, the other is
    #: derived from the therapy's own regimen rather than assumed.
    annual_cost: float | None = Field(default=None, gt=0)
    note: str | None = None


class PriceEditRequest(BaseModel):
    edits: list[PriceEdit]


# --------------------------------------------------------------------------- M19 import


class ImportIssue(BaseModel):
    """One rejected cell, addressed the way a spreadsheet addresses it.

    `sheet`, `row` and `column` rather than a field name: the person fixing
    this is looking at the workbook, not at the API, and "row 14, column
    `unit_price`" is an instruction while "validation error on
    `edits.3.unit_price`" is a puzzle.
    """

    sheet: str
    row: int
    column: str
    value: str | None
    message: str
    severity: Literal["error", "warning"] = "error"


class ImportedScenario(BaseModel):
    """A scenario draft parsed out of a workbook, before it is saved.

    Returned rather than persisted. An import that silently created a scenario
    would give the analyst no chance to see what the file was read as — and
    every value here carries its sheet and row as provenance precisely so that
    review is possible.
    """

    name: str | None = None
    asset_name: str | None = None
    indication_id: int | None = None
    launch_year: int | None = None
    horizon_years: int | None = None
    reporting_currency: str | None = None
    country_codes: list[str] = Field(default_factory=list)
    perspective: str | None = None
    covered_population: int | None = None
    subgroup_codes: list[str] = Field(default_factory=list)
    overrides: list[dict[str, object]] = Field(default_factory=list)
    prices: list[PriceEdit] = Field(default_factory=list)


class ImportResponse(BaseModel):
    """What a workbook parsed to, and everything wrong with it.

    Both halves are always present. A file with three good sheets and one bad
    row should not be rejected wholesale — the analyst wants the 97% that
    parsed and a precise pointer at the 3% that did not.
    """

    scenario: ImportedScenario
    issues: list[ImportIssue] = Field(default_factory=list)
    rows_read: int = 0
    accepted: bool = True
