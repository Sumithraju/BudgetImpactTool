"""M6's slice of the canonical golden case — docs/modules/README.md.

The fixture is frozen and synthetic (Germany/obesity/2028), not live reference
data. It must not be "corrected" to match what the live pipeline derives
today — that is the fixture's whole point. Changing this file requires a
biet_engine version bump and a written justification, per the skill's testing
section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from biet_engine.persistence import persistence_fraction

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deu_obesity_2028.json"


@pytest.fixture
def golden_case() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_golden_case_persistence_fraction(golden_case: dict) -> None:
    f = persistence_fraction(golden_case["persistence_p12"])
    assert f == pytest.approx(golden_case["persistence_fraction"], abs=1e-4)
