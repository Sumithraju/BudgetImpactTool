"""The comparator workbook contract — M19 sections 5.1 to 5.3.

Column labels are matched by *label*, not by position: an analyst who inserts
a column must not silently shift every value one place (M19 section 5.1).

Every rate column declares its unit in its own header. Rates are fractions
internally (non-negotiable 5), so this module is the one boundary where a
percentage becomes a fraction, and it converts exactly once.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class WorkbookColumn(StrEnum):
    """Header labels, exactly as they must appear in the file."""

    NAME = "Name"
    TYPE = "Type"
    MARKET = "Market"
    CURRENCY = "Currency"
    MARKET_SHARE_PCT = "Market share (%)"
    DRUG_COST = "Drug cost / year"
    ADMIN_COST = "Administration / year"
    MONITORING_COST = "Monitoring / year"
    AE_COST = "AE management / year"
    SOURCE = "Source"
    TIER = "Tier"


REQUIRED_COLUMNS: Final[tuple[WorkbookColumn, ...]] = (
    WorkbookColumn.NAME,
    WorkbookColumn.MARKET,
    WorkbookColumn.CURRENCY,
    WorkbookColumn.MARKET_SHARE_PCT,
    WorkbookColumn.DRUG_COST,
)

#: Absent means zero — a comparator with no administration cost is ordinary.
OPTIONAL_COST_COLUMNS: Final[tuple[WorkbookColumn, ...]] = (
    WorkbookColumn.ADMIN_COST,
    WorkbookColumn.MONITORING_COST,
    WorkbookColumn.AE_COST,
)


class SubgroupColumn(StrEnum):
    """The subgroup share sheet — two columns, matched by label."""

    SUBGROUP = "Subgroup"
    SHARE_PCT = "Share (%)"
    SOURCE = "Source"
    TIER = "Tier"


REQUIRED_SUBGROUP_COLUMNS: Final[tuple[SubgroupColumn, ...]] = (
    SubgroupColumn.SUBGROUP,
    SubgroupColumn.SHARE_PCT,
)


class FindingSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class FindingCode(StrEnum):
    """Every finding a comparator import can raise. M19 section 5.3."""

    NOT_A_WORKBOOK = "NOT_A_WORKBOOK"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    NO_CACHED_VALUE = "NO_CACHED_VALUE"
    MISSING_COLUMN = "MISSING_COLUMN"
    UNRECOGNISED_COLUMN = "UNRECOGNISED_COLUMN"
    MISSING_VALUE = "MISSING_VALUE"
    NOT_A_NUMBER = "NOT_A_NUMBER"
    NEGATIVE_COST = "NEGATIVE_COST"
    AMBIGUOUS_RATE_UNIT = "AMBIGUOUS_RATE_UNIT"
    SHARES_DO_NOT_SUM = "SHARES_DO_NOT_SUM"
    SHARES_NORMALISED = "SHARES_NORMALISED"
    UNKNOWN_MARKET = "UNKNOWN_MARKET"
    UNKNOWN_CURRENCY = "UNKNOWN_CURRENCY"
    MIXED_CURRENCY_COLUMN = "MIXED_CURRENCY_COLUMN"
    DUPLICATE_ROW = "DUPLICATE_ROW"
    UNKNOWN_TIER = "UNKNOWN_TIER"
    NO_ROWS = "NO_ROWS"
    UNKNOWN_SUBGROUP = "UNKNOWN_SUBGROUP"
    SUBGROUP_NOT_SUPPLIABLE = "SUBGROUP_NOT_SUPPLIABLE"
    SUBGROUP_SHARES_EXCEED_ONE = "SUBGROUP_SHARES_EXCEED_ONE"


#: Shares this far off 1.0 are normalised with a warning; further is rejected.
#: Half a percentage point is rounding in a spreadsheet; six points is a
#: missing row, and using it anyway would silently misprice the baseline.
SHARE_TOLERANCE: Final[float] = 0.005

MAX_UPLOAD_BYTES: Final[int] = 2 * 1024 * 1024
MAX_ROWS: Final[int] = 500

PERCENT_DIVISOR: Final[float] = 100.0

#: An imported value has no published basis until someone states one.
DEFAULT_IMPORT_TIER: Final[str] = "D"
VALID_TIERS: Final[frozenset[str]] = frozenset({"A", "B", "C", "D"})

CSV_SHEET_NAME: Final[str] = "CSV"
