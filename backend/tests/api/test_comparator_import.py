"""Comparator workbook import — M19 sections 5.1 to 5.6.

The parser is deliberately testable without a session: import is a pure
transformation from bytes to a result, and what happens to an accepted row
afterwards is the caller's decision.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from biet_api.constants.workbook import FindingCode, FindingSeverity
from biet_api.services.comparator_import_service import ComparatorImportService

MARKETS = frozenset({"USA", "DEU", "GBR"})
CURRENCIES = frozenset({"USD", "EUR", "GBP"})

HEADER = (
    "Name,Type,Market,Currency,Market share (%),Drug cost / year,"
    "Administration / year,Monitoring / year,AE management / year,Source,Tier"
)


@pytest.fixture
def service() -> ComparatorImportService:
    return ComparatorImportService(MARKETS, CURRENCIES)


def csv_of(*rows: str) -> bytes:
    return ("\n".join((HEADER, *rows)) + "\n").encode()


def codes(result) -> set[FindingCode]:
    return {f.code for f in result.findings}


# ------------------------------------------------------------ happy path


def test_valid_file_is_accepted_and_shares_become_fractions(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,40,1200,0,150,60,EMA,B",
            "Saxenda,Comparator,DEU,EUR,60,2400,0,150,90,EMA,B",
        ),
        "c.csv",
    )
    assert result.accepted
    assert [c.market_share for c in result.comparators] == [0.40, 0.60]


def test_total_cost_is_the_sum_of_its_four_components(service):
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,1200,10,150,60,EMA,B"), "c.csv")
    (comparator,) = result.comparators
    assert comparator.total_cost == pytest.approx(1200 + 10 + 150 + 60)


def test_an_imported_value_carries_its_sheet_and_cell(service):
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,1200,0,0,0,EMA,B"), "c.csv")
    assert result.comparators[0].origin == "CSV!A2"


def test_a_row_with_no_stated_source_is_tier_d(service):
    """A number typed into a spreadsheet has no published basis until someone
    states one — M19 section 5.5."""
    result = service.parse(csv_of("Lifestyle,Other,DEU,EUR,100,400,0,0,0,,"), "c.csv")
    assert result.comparators[0].confidence_tier == "D"


def test_a_stated_tier_is_honoured(service):
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,1200,0,0,0,EMA,B"), "c.csv")
    assert result.comparators[0].confidence_tier == "B"


def test_an_unknown_tier_falls_back_to_d_with_a_warning(service):
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,1200,0,0,0,EMA,Z"), "c.csv")
    assert result.accepted
    assert result.comparators[0].confidence_tier == "D"
    assert FindingCode.UNKNOWN_TIER in codes(result)


# ------------------------------------------------------------------ units


def test_a_share_above_100_in_a_percent_column_is_rejected_not_coerced(service):
    """Believing the declared unit is the whole point: coercing 4000 to 40
    would silently invent a market share."""
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,4000,1200,0,0,0,EMA,B"), "c.csv")
    assert not result.accepted
    assert FindingCode.AMBIGUOUS_RATE_UNIT in codes(result)


def test_a_fraction_in_a_percent_column_is_read_as_a_percentage(service):
    """0.40 in a `(%)` column means 0.4%, not 40%. It is believed, and the
    share total is what catches the mistake."""
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,0.40,1200,0,0,0,EMA,B"), "c.csv")
    assert not result.accepted
    assert FindingCode.SHARES_DO_NOT_SUM in codes(result)


# ----------------------------------------------------------------- shares


def test_shares_within_tolerance_are_normalised_with_a_warning(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,40,1200,0,0,0,EMA,B",
            "Saxenda,Comparator,DEU,EUR,59.7,2400,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert result.accepted
    assert FindingCode.SHARES_NORMALISED in codes(result)


def test_shares_beyond_tolerance_reject_the_file(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,40,1200,0,0,0,EMA,B",
            "Saxenda,Comparator,DEU,EUR,54,2400,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert not result.accepted
    assert FindingCode.SHARES_DO_NOT_SUM in codes(result)


def test_shares_are_totalled_per_market_not_across_them(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,100,1200,0,0,0,EMA,B",
            "Wegovy,SoC,USA,USD,100,13000,0,0,0,NADAC,B",
        ),
        "c.csv",
    )
    assert result.accepted
    assert result.share_totals == {"DEU": pytest.approx(1.0), "USA": pytest.approx(1.0)}


# ------------------------------------------------------- whole-file reject


def test_every_finding_is_returned_in_one_pass(service):
    """Fifty errors should be fifty messages once, not fifty round trips
    (M19 section 5.4)."""
    result = service.parse(
        csv_of(
            ",SoC,DEU,EUR,25,1200,0,0,0,EMA,B",
            "Saxenda,Comparator,XXX,EUR,25,2400,0,0,0,EMA,B",
            "Trulicity,Comparator,DEU,EUR,25,abc,0,0,0,EMA,B",
            "Victoza,Comparator,DEU,ZZZ,25,900,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert not result.accepted
    assert {
        FindingCode.MISSING_VALUE,
        FindingCode.UNKNOWN_MARKET,
        FindingCode.NOT_A_NUMBER,
        FindingCode.UNKNOWN_CURRENCY,
    } <= codes(result)


def test_one_error_anywhere_means_nothing_is_imported(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,50,1200,0,0,0,EMA,B",
            "Saxenda,Comparator,XXX,EUR,50,2400,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert not result.accepted
    assert result.comparators == ()


def test_an_unreadable_cell_raises_one_finding_not_two(service):
    """`NOT_A_NUMBER` and `MISSING_VALUE` for the same cell is noise."""
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,abc,0,0,0,EMA,B"), "c.csv")
    drug_cost_findings = [f for f in result.findings if f.ref and f.ref.cell == "F2"]
    assert len(drug_cost_findings) == 1
    assert drug_cost_findings[0].code is FindingCode.NOT_A_NUMBER


def test_a_duplicate_row_names_both_lines(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,50,1200,0,0,0,EMA,B",
            "ozempic,Comparator,DEU,EUR,50,1300,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert not result.accepted
    duplicate = next(f for f in result.findings if f.code is FindingCode.DUPLICATE_ROW)
    assert "2" in duplicate.message and "3" in duplicate.message


def test_one_market_priced_in_two_currencies_is_rejected(service):
    result = service.parse(
        csv_of(
            "Ozempic,SoC,DEU,EUR,50,1200,0,0,0,EMA,B",
            "Saxenda,Comparator,DEU,USD,50,2400,0,0,0,EMA,B",
        ),
        "c.csv",
    )
    assert not result.accepted
    assert FindingCode.MIXED_CURRENCY_COLUMN in codes(result)


def test_a_negative_cost_is_rejected(service):
    result = service.parse(csv_of("Ozempic,SoC,DEU,EUR,100,-1200,0,0,0,EMA,B"), "c.csv")
    assert not result.accepted
    assert FindingCode.NEGATIVE_COST in codes(result)


# ---------------------------------------------------------------- columns


def test_a_missing_required_column_names_it(service):
    result = service.parse(b"Name,Market,Currency\nOzempic,DEU,EUR\n", "c.csv")
    assert not result.accepted
    missing = {f.expected for f in result.findings if f.code is FindingCode.MISSING_COLUMN}
    assert {"Market share (%)", "Drug cost / year"} <= missing


def test_columns_are_matched_by_label_not_position(service):
    """An inserted column must not shift every value one place."""
    result = service.parse(
        b"Internal ID,Currency,Name,Market,Drug cost / year,Market share (%)\n"
        b"X-1,EUR,Ozempic,DEU,1200,100\n",
        "c.csv",
    )
    assert result.accepted
    assert result.comparators[0].drug_cost == 1200
    assert result.comparators[0].market_share == 1.0


def test_an_unrecognised_column_warns_and_is_ignored(service):
    result = service.parse(
        b"Name,Market,Currency,Market share (%),Drug cost / year,Notes\n"
        b"Ozempic,DEU,EUR,100,1200,anything\n",
        "c.csv",
    )
    assert result.accepted
    assert FindingCode.UNRECOGNISED_COLUMN in codes(result)


def test_optional_cost_columns_absent_default_to_zero(service):
    result = service.parse(
        b"Name,Market,Currency,Market share (%),Drug cost / year\n"
        b"Ozempic,DEU,EUR,100,1200\n",
        "c.csv",
    )
    assert result.accepted
    assert result.comparators[0].admin_cost == 0.0
    assert result.comparators[0].total_cost == 1200


# ------------------------------------------------------------- file kinds


def test_an_xlsx_is_read_and_its_sheet_name_reaches_provenance(service):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Comparators"
    sheet.append(["Name", "Market", "Currency", "Market share (%)", "Drug cost / year"])
    sheet.append(["Ozempic", "DEU", "EUR", 100, 1200])
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = service.parse(buffer.getvalue(), "model.xlsx")
    assert result.accepted
    assert result.sheet == "Comparators"
    assert result.comparators[0].origin == "Comparators!A2"


def test_an_empty_file_is_rejected(service):
    result = service.parse(b"", "empty.csv")
    assert not result.accepted
    assert FindingCode.EMPTY_FILE in codes(result)


def test_a_header_with_no_rows_beneath_it_is_rejected(service):
    result = service.parse(csv_of(), "c.csv")
    assert not result.accepted
    assert FindingCode.NO_ROWS in codes(result)


def test_a_file_that_is_not_a_workbook_is_rejected(service):
    result = service.parse(b"\x89PNG\r\n\x1a\n\x00\x01\xff\xfe", "logo.png")
    assert not result.accepted
    assert FindingCode.NOT_A_WORKBOOK in codes(result)


def test_an_oversized_file_is_rejected_before_parsing(service):
    from biet_api.constants.workbook import MAX_UPLOAD_BYTES

    result = service.parse(b"x" * (MAX_UPLOAD_BYTES + 1), "huge.csv")
    assert not result.accepted
    assert FindingCode.FILE_TOO_LARGE in codes(result)


def test_a_number_stored_as_text_with_a_thousands_separator_is_read(service):
    result = service.parse(csv_of('Ozempic,SoC,DEU,EUR,100,"1,200",0,0,0,EMA,B'), "c.csv")
    assert result.accepted
    assert result.comparators[0].drug_cost == 1200.0


def test_every_finding_that_concerns_a_cell_carries_its_reference(service):
    result = service.parse(csv_of("Ozempic,SoC,XXX,EUR,100,1200,0,0,0,EMA,B"), "c.csv")
    market = next(f for f in result.findings if f.code is FindingCode.UNKNOWN_MARKET)
    assert market.ref is not None
    assert market.ref.cell == "C2"
    assert market.severity is FindingSeverity.ERROR
