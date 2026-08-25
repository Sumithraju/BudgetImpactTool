"""API schemas for comparator workbook import — M19 section 4.

The HTTP shape only. Nothing here is persisted directly and nothing here
reaches the engine (biet-backend skill section 3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..constants.workbook import FindingCode, FindingSeverity


class CellRef(BaseModel):
    """Every finding points here. A message without one is not actionable."""

    model_config = ConfigDict(frozen=True)

    sheet: str
    cell: str                                   # "C7"
    column_label: str | None = None
    row_number: int | None = None


class ImportFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: FindingSeverity
    code: FindingCode
    message: str                                # the analyst's language, not the parser's
    ref: CellRef | None = None
    supplied: str | None = None
    expected: str | None = None


class ImportedComparator(BaseModel):
    """One validated row. Rates are fractions by the time they get here."""

    model_config = ConfigDict(frozen=True)

    name: str
    therapy_type: str | None = None
    country_code: str
    currency_code: str
    market_share: float = Field(ge=0.0, le=1.0)
    drug_cost: float = Field(ge=0.0)
    admin_cost: float = Field(ge=0.0)
    monitoring_cost: float = Field(ge=0.0)
    ae_cost: float = Field(ge=0.0)
    total_cost: float = Field(ge=0.0)
    source: str
    confidence_tier: str = Field(min_length=1, max_length=1)
    #: "<Sheet>!<Cell>" of this row's name cell — M19 section 5.5.
    origin: str


class ComparatorImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    filename: str
    sheet: str
    rows_read: int
    findings: tuple[ImportFinding, ...] = ()
    comparators: tuple[ImportedComparator, ...] = ()
    #: Per market, the share total found before any normalisation.
    share_totals: dict[str, float] = Field(default_factory=dict)
