"""Subgroup share import — M18 section 5.2 through M19's file contract.

Two columns: which subgroup, and what share of the adult obesity population it
accounts for. The rules that make the partition a partition are enforced here
rather than left to the caller, because a sheet is exactly where they get
broken: obesity alone is the derived residual and cannot be supplied,
paediatric obesity is disjoint and has its own denominator, and the supplied
shares must leave a residual.
"""

from __future__ import annotations

from typing import Any, Final

from biet_engine.constants import SUPPLIED_SUBGROUPS, Subgroup

from ..constants.subgroups import SUBGROUP_LABELS
from ..constants.workbook import (
    DEFAULT_IMPORT_TIER,
    PERCENT_DIVISOR,
    REQUIRED_SUBGROUP_COLUMNS,
    VALID_TIERS,
    FindingCode,
    FindingSeverity,
    SubgroupColumn,
)
from ..schemas.comparator_import import ImportedSubgroupShare, SubgroupImportResult
from .workbook_reader import HEADER_ROW, FindingCollector, column_letter, read_table

MAX_PERCENT: Final[float] = 100.0

#: Accept the machine code or the human label, case- and space-insensitively.
#: An analyst editing an exported sheet will type the label; a script will
#: emit the code, and refusing either would be pedantry.
_BY_CODE: Final[dict[str, Subgroup]] = {s.value.casefold(): s for s in Subgroup}
_BY_LABEL: Final[dict[str, Subgroup]] = {
    label.casefold(): subgroup for subgroup, label in SUBGROUP_LABELS.items()
}


def _resolve(text: str) -> Subgroup | None:
    key = text.strip().casefold()
    return _BY_CODE.get(key) or _BY_LABEL.get(key)


class SubgroupImportService:
    """Parses an uploaded subgroup share sheet. Holds no session."""

    def parse(self, data: bytes, filename: str) -> SubgroupImportResult:
        collector = FindingCollector()
        table = read_table(data, collector)
        if table is None:
            return self._reject(filename, collector)

        index = self._map_columns(table.header, collector)
        if collector.has_error:
            return self._reject(filename, collector)

        if not table.rows:
            collector.add(
                FindingSeverity.ERROR, FindingCode.NO_ROWS,
                "The file has a header row but no subgroups beneath it.",
            )
            return self._reject(filename, collector)

        shares = self._read_rows(table.rows, index, collector)
        total = sum(s.share for s in shares)

        # The residual is what makes the five a partition. Without one there is
        # no room for obesity alone, and the split stops describing everybody.
        if total >= 1.0:
            collector.add(
                FindingSeverity.ERROR, FindingCode.SUBGROUP_SHARES_EXCEED_ONE,
                f"The supplied shares total {total * PERCENT_DIVISOR:.1f}%, leaving nothing "
                f"for {SUBGROUP_LABELS[Subgroup.OBESITY_ALONE].lower()}. They must total "
                f"less than 100%.",
                supplied=f"{total * PERCENT_DIVISOR:.1f}%",
                expected="less than 100%",
            )

        if collector.has_error:
            return self._reject(filename, collector, rows_read=len(table.rows))

        return SubgroupImportResult(
            accepted=True,
            filename=filename,
            sheet=collector.sheet,
            rows_read=len(table.rows),
            findings=tuple(collector.findings),
            shares=tuple(shares),
            residual_share=1.0 - total,
        )

    # ---------------------------------------------------------------- pieces

    def _reject(
        self, filename: str, collector: FindingCollector, *, rows_read: int = 0
    ) -> SubgroupImportResult:
        return SubgroupImportResult(
            accepted=False, filename=filename, sheet=collector.sheet,
            rows_read=rows_read, findings=tuple(collector.findings),
        )

    def _map_columns(
        self, header: list[str], collector: FindingCollector
    ) -> dict[SubgroupColumn, int]:
        known = {c.value.casefold(): c for c in SubgroupColumn}
        index: dict[SubgroupColumn, int] = {}

        for position, label in enumerate(header):
            column = known.get(label.casefold())
            if column is None:
                if label:
                    collector.add(
                        FindingSeverity.WARNING, FindingCode.UNRECOGNISED_COLUMN,
                        f"Column {label!r} is not part of the subgroup contract "
                        f"and was ignored.",
                        ref=collector.cell(position, HEADER_ROW, label),
                    )
                continue
            index[column] = position

        for required in REQUIRED_SUBGROUP_COLUMNS:
            if required not in index:
                collector.add(
                    FindingSeverity.ERROR, FindingCode.MISSING_COLUMN,
                    f"The sheet has no {required.value!r} column.",
                    expected=required.value,
                )
        return index

    def _read_rows(
        self,
        rows: list[list[Any]],
        index: dict[SubgroupColumn, int],
        collector: FindingCollector,
    ) -> list[ImportedSubgroupShare]:
        out: list[ImportedSubgroupShare] = []
        seen: set[Subgroup] = set()

        for offset, row in enumerate(rows):
            row_number = offset + HEADER_ROW + 1
            raw_name = self._raw(row, index, SubgroupColumn.SUBGROUP)
            name = "" if raw_name is None else str(raw_name).strip()
            name_cell = collector.cell(
                index[SubgroupColumn.SUBGROUP], row_number, SubgroupColumn.SUBGROUP.value
            )

            if not name:
                collector.add(
                    FindingSeverity.ERROR, FindingCode.MISSING_VALUE,
                    "Subgroup is blank.", ref=name_cell,
                )
                continue

            subgroup = _resolve(name)
            if subgroup is None:
                collector.add(
                    FindingSeverity.ERROR, FindingCode.UNKNOWN_SUBGROUP,
                    f"{name!r} is not a subgroup this tool models.",
                    ref=name_cell, supplied=name,
                    expected=", ".join(s.value for s in SUPPLIED_SUBGROUPS),
                )
                continue

            if subgroup not in SUPPLIED_SUBGROUPS:
                reason = (
                    "is the derived residual and is computed from the others"
                    if subgroup is Subgroup.OBESITY_ALONE
                    else "has its own denominator and is not part of the adult split"
                )
                collector.add(
                    FindingSeverity.ERROR, FindingCode.SUBGROUP_NOT_SUPPLIABLE,
                    f"{SUBGROUP_LABELS[subgroup]} {reason}, so it cannot be given a "
                    f"share here.",
                    ref=name_cell, supplied=name,
                )
                continue

            if subgroup in seen:
                collector.add(
                    FindingSeverity.ERROR, FindingCode.DUPLICATE_ROW,
                    f"{SUBGROUP_LABELS[subgroup]} appears more than once.",
                    ref=name_cell,
                )
                continue
            seen.add(subgroup)

            share = self._share(row, index, row_number, collector)
            if share is None:
                continue

            out.append(
                ImportedSubgroupShare(
                    code=subgroup.value,
                    share=share,
                    source=self._source(row, index, row_number),
                    confidence_tier=self._tier(row, index, row_number, collector),
                    origin=f"{collector.sheet}!"
                           f"{column_letter(index[SubgroupColumn.SUBGROUP])}{row_number}",
                )
            )
        return out

    def _raw(
        self, row: list[Any], index: dict[SubgroupColumn, int], column: SubgroupColumn
    ) -> Any:
        position = index.get(column)
        if position is None or position >= len(row):
            return None
        return row[position]

    def _share(
        self,
        row: list[Any],
        index: dict[SubgroupColumn, int],
        row_number: int,
        collector: FindingCollector,
    ) -> float | None:
        column = SubgroupColumn.SHARE_PCT
        cell = collector.cell(index[column], row_number, column.value)
        value = self._raw(row, index, column)

        if value is None or str(value).strip() == "":
            collector.add(
                FindingSeverity.ERROR, FindingCode.MISSING_VALUE,
                f"{column.value} is blank.", ref=cell,
            )
            return None

        try:
            percent = float(str(value).replace(",", "").strip())
        except ValueError:
            collector.add(
                FindingSeverity.ERROR, FindingCode.NOT_A_NUMBER,
                f"{column.value} is not a number.", ref=cell, supplied=str(value),
            )
            return None

        if percent < 0 or percent > MAX_PERCENT:
            collector.add(
                FindingSeverity.ERROR, FindingCode.AMBIGUOUS_RATE_UNIT,
                f"{percent:g} cannot be a percentage. This column is labelled "
                f"'{column.value}', so 19 means 19% and 0.19 means 0.19%.",
                ref=cell, supplied=f"{percent:g}", expected="0 to 100",
            )
            return None

        return percent / PERCENT_DIVISOR

    def _source(
        self, row: list[Any], index: dict[SubgroupColumn, int], row_number: int
    ) -> str:
        stated = self._raw(row, index, SubgroupColumn.SOURCE)
        text = "" if stated is None else str(stated).strip()
        return text or f"workbook row {row_number}"

    def _tier(
        self,
        row: list[Any],
        index: dict[SubgroupColumn, int],
        row_number: int,
        collector: FindingCollector,
    ) -> str:
        stated = self._raw(row, index, SubgroupColumn.TIER)
        if stated is None or not str(stated).strip():
            return DEFAULT_IMPORT_TIER
        tier = str(stated).strip().upper()
        if tier not in VALID_TIERS:
            collector.add(
                FindingSeverity.WARNING, FindingCode.UNKNOWN_TIER,
                f"{tier!r} is not a confidence tier; this row was recorded as "
                f"tier {DEFAULT_IMPORT_TIER}.",
                ref=collector.cell(
                    index.get(SubgroupColumn.TIER, 0), row_number, SubgroupColumn.TIER.value
                ),
                supplied=tier, expected="A, B, C or D",
            )
            return DEFAULT_IMPORT_TIER
        return tier
