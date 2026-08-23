"""M3's slice of the canonical golden case — docs/modules/README.md.

See test_persistence_golden.py for the fixture provenance note. The fixture
records only the pre-combined `criterion_stack` value, not a real criterion
composition, so `test_golden_case_combined_factor` in test_eligibility.py
already covers the mechanical case. This file instead verifies M2 and M3
compose correctly end to end: combine_criteria's output feeding directly into
compute_funnel still reproduces the golden addressable population.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from biet_engine.eligibility import combine_criteria
from biet_engine.funnel import compute_funnel

from ..conftest import make_country_input, make_criterion

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deu_obesity_2028.json"


@pytest.fixture
def golden_case() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_golden_case_eligibility_into_funnel(golden_case: dict) -> None:
    criteria_result = combine_criteria(
        [make_criterion("synthetic_stack", golden_case["criterion_stack"])]
    )
    country = make_country_input(
        country_code=golden_case["country_code"],
        population_total=golden_case["total_population"],
        adult_share=golden_case["adult_share"],
        prevalence=golden_case["obesity_prevalence"],
        diagnosis_rate=golden_case["diagnosis_rate"],
        treatment_rate=golden_case["treatment_rate"],
        access_rate=golden_case["access_rate"],
    )
    result = compute_funnel(country, criteria_result.combined_factor, year=1)

    assert result.addressable == pytest.approx(golden_case["addressable"], abs=1.0)
