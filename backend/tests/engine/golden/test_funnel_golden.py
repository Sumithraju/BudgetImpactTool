"""M2's slice of the canonical golden case — docs/modules/README.md.

See test_persistence_golden.py for the fixture provenance note; the same
frozen fixture is reused here for the funnel-relevant fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from biet_engine.funnel import compute_funnel

from ..conftest import make_country_input, make_valued

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deu_obesity_2028.json"


@pytest.fixture
def golden_case() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_golden_case_funnel_addressable(golden_case: dict) -> None:
    country = make_country_input(
        country_code=golden_case["country_code"],
        population_total=golden_case["total_population"],
        adult_share=golden_case["adult_share"],
        prevalence=golden_case["obesity_prevalence"],
        diagnosis_rate=golden_case["diagnosis_rate"],
        treatment_rate=golden_case["treatment_rate"],
        access_rate=golden_case["access_rate"],
    )
    result = compute_funnel(
        country, make_valued(golden_case["criterion_stack"]), year=1,
    )

    assert result.addressable == pytest.approx(golden_case["addressable"], abs=1.0)
