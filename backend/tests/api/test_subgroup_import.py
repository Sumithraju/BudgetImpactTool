"""Subgroup share import — M18 section 5.2 under M19's file contract."""

from __future__ import annotations

import pytest

from biet_api.constants.workbook import FindingCode
from biet_api.services.subgroup_import_service import SubgroupImportService

HEADER = "Subgroup,Share (%),Source,Tier"


@pytest.fixture
def service() -> SubgroupImportService:
    return SubgroupImportService()


def csv_of(*rows: str) -> bytes:
    return ("\n".join((HEADER, *rows)) + "\n").encode()


def codes(result) -> set[FindingCode]:
    return {f.code for f in result.findings}


def test_a_valid_sheet_is_accepted_and_shares_become_fractions(service):
    result = service.parse(
        csv_of(
            "obesity_established_cvd,10,registry,B",
            "obesity_t2d,22,survey,B",
        ),
        "s.csv",
    )
    assert result.accepted
    assert [s.share for s in result.shares] == [0.10, 0.22]


def test_the_residual_is_one_minus_the_supplied_total(service):
    result = service.parse(
        csv_of(
            "obesity_established_cvd,8,,",
            "obesity_t2d,19,,",
            "obesity_hypertension,30,,",
            "obesity_dyslipidaemia,13,,",
        ),
        "s.csv",
    )
    assert result.residual_share == pytest.approx(0.30)


def test_a_subgroup_may_be_named_by_its_human_label(service):
    """An analyst editing an exported sheet types the label; refusing it
    would be pedantry."""
    result = service.parse(csv_of("Obesity with type 2 diabetes,22,,"), "s.csv")
    assert result.accepted
    assert result.shares[0].code == "obesity_t2d"


def test_supplying_the_residual_is_rejected(service):
    result = service.parse(csv_of("obesity_alone,30,,"), "s.csv")
    assert not result.accepted
    assert FindingCode.SUBGROUP_NOT_SUPPLIABLE in codes(result)


def test_supplying_the_paediatric_segment_is_rejected(service):
    """It has its own denominator and is not part of the adult split."""
    result = service.parse(csv_of("paediatric_obesity,5,,"), "s.csv")
    assert not result.accepted
    assert FindingCode.SUBGROUP_NOT_SUPPLIABLE in codes(result)


def test_shares_reaching_one_leave_no_residual_and_are_rejected(service):
    result = service.parse(
        csv_of("obesity_t2d,50,,", "obesity_hypertension,50,,"), "s.csv"
    )
    assert not result.accepted
    assert FindingCode.SUBGROUP_SHARES_EXCEED_ONE in codes(result)


def test_an_unknown_subgroup_names_what_is_accepted(service):
    result = service.parse(csv_of("obesity_gout,5,,"), "s.csv")
    assert not result.accepted
    finding = next(f for f in result.findings if f.code is FindingCode.UNKNOWN_SUBGROUP)
    assert "obesity_t2d" in (finding.expected or "")


def test_a_duplicated_subgroup_is_rejected(service):
    result = service.parse(csv_of("obesity_t2d,20,,", "obesity_t2d,10,,"), "s.csv")
    assert not result.accepted
    assert FindingCode.DUPLICATE_ROW in codes(result)


def test_a_share_above_100_is_rejected_not_coerced(service):
    result = service.parse(csv_of("obesity_t2d,2200,,"), "s.csv")
    assert not result.accepted
    assert FindingCode.AMBIGUOUS_RATE_UNIT in codes(result)


def test_a_row_with_no_stated_source_is_tier_d(service):
    result = service.parse(csv_of("obesity_t2d,22,,"), "s.csv")
    assert result.shares[0].confidence_tier == "D"


def test_findings_carry_the_cell_that_caused_them(service):
    result = service.parse(csv_of("obesity_gout,5,,"), "s.csv")
    finding = next(f for f in result.findings if f.code is FindingCode.UNKNOWN_SUBGROUP)
    assert finding.ref is not None
    assert finding.ref.cell == "A2"


def test_a_missing_required_column_names_it(service):
    result = service.parse(b"Subgroup\nobesity_t2d\n", "s.csv")
    assert not result.accepted
    assert FindingCode.MISSING_COLUMN in codes(result)


def test_one_error_anywhere_means_nothing_is_imported(service):
    result = service.parse(csv_of("obesity_t2d,20,,", "obesity_gout,10,,"), "s.csv")
    assert not result.accepted
    assert result.shares == ()


def test_every_imported_share_carries_its_origin_cell(service):
    result = service.parse(csv_of("obesity_t2d,22,,"), "s.csv")
    assert result.shares[0].origin == "CSV!A2"
