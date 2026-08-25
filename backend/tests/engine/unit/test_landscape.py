"""Unit tests for biet_engine.landscape — M14 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import MAX_ENTRANT_TOTAL_SHARE
from biet_engine.exceptions import DisplacementError
from biet_engine.landscape import (
    entrant_share,
    expected_entry_year,
    project_landscape,
)
from biet_engine.models import PipelineEntrant

from ..conftest import make_valued

BASELINE = {1: (0.5, 0.5, 0.5), 2: (0.3, 0.3, 0.3), 3: (0.2, 0.2, 0.2)}


def _entrant(
    drug_id: int = 9, entry_year: int = 2, share: float = 0.20, ramp: int = 2,
) -> PipelineEntrant:
    return PipelineEntrant(
        drug_id=drug_id, name=f"ENTRANT-{drug_id}", entry_year=entry_year,
        terminal_share=make_valued(share), ramp_years=ramp,
    )


# --------------------------------------------------------------------------- entry year


def test_entry_year_from_completion_plus_lag() -> None:
    """Completes 2027, 1.5-year lag, asset launches 2028: approved mid-2028,
    so year 2 of a launch-relative horizon."""
    assert expected_entry_year(2027, launch_year=2028, regulatory_lag_years=1.5) == 2


def test_a_completion_already_past_clamps_to_year_one() -> None:
    """An entrant already marketed when this asset launches is an incumbent,
    and belongs in the baseline from the start rather than at a negative
    year."""
    assert expected_entry_year(2020, launch_year=2028, regulatory_lag_years=1.5) == 1


def test_a_longer_lag_pushes_entry_later() -> None:
    early = expected_entry_year(2027, launch_year=2028, regulatory_lag_years=1.0)
    late = expected_entry_year(2027, launch_year=2028, regulatory_lag_years=3.0)
    assert late > early


# --------------------------------------------------------------------------- ramp


def test_share_is_exactly_zero_before_entry() -> None:
    entrant = _entrant(entry_year=3)
    assert entrant_share(entrant, 1) == 0.0
    assert entrant_share(entrant, 2) == 0.0
    assert entrant_share(entrant, 3) > 0.0


def test_ramp_reaches_plateau_at_entry_plus_ramp_minus_one() -> None:
    entrant = _entrant(entry_year=2, share=0.30, ramp=3)
    assert entrant_share(entrant, 2) == pytest.approx(0.10)
    assert entrant_share(entrant, 3) == pytest.approx(0.20)
    assert entrant_share(entrant, 4) == pytest.approx(0.30)


def test_the_plateau_is_a_ceiling_not_a_trend() -> None:
    entrant = _entrant(entry_year=1, share=0.25, ramp=2)
    assert entrant_share(entrant, 10) == pytest.approx(0.25)


# --------------------------------------------------------------------------- projection


def test_no_entrants_returns_the_baseline_untouched() -> None:
    """The ordinary case, and deliberately silent — a scenario with no
    entrants is not a degraded scenario."""
    result = project_landscape(BASELINE, [], horizon_years=3)
    assert result.baseline_shares == BASELINE
    assert result.admitted == ()
    assert result.warnings == ()


def test_shares_sum_to_one_at_every_year() -> None:
    result = project_landscape(BASELINE, [_entrant()], horizon_years=3)
    for year in range(3):
        total = sum(v[year] for v in result.baseline_shares.values())
        assert total == pytest.approx(1.0)


def test_incumbents_are_rescaled_proportionally() -> None:
    """No public source says which incumbent an entrant displaces, so it
    takes from all of them in proportion. Their ratios to each other must
    therefore be unchanged."""
    result = project_landscape(BASELINE, [_entrant()], horizon_years=3)
    shares = result.baseline_shares
    before = BASELINE[1][2] / BASELINE[2][2]
    after = shares[1][2] / shares[2][2]
    assert after == pytest.approx(before)


def test_an_entrant_beyond_the_horizon_is_not_modelled() -> None:
    """It cannot affect a result that finishes before it arrives, and a row
    of zeros would suggest it was weighed and found immaterial."""
    result = project_landscape(BASELINE, [_entrant(entry_year=5)], horizon_years=3)
    assert result.admitted == ()
    assert result.baseline_shares == BASELINE


def test_admission_warns_and_names_every_entrant() -> None:
    result = project_landscape(BASELINE, [_entrant()], horizon_years=3)
    codes = {w.code for w in result.warnings}
    assert "PIPELINE_ENTRANT_MODELLED" in codes
    assert "ENTRANT-9" in " ".join(w.message for w in result.warnings)


def test_entrant_total_above_the_cap_is_scaled_down_and_warned() -> None:
    """An uncapped total leaves a world-without made entirely of drugs that
    do not yet exist, which is not a market and not a comparison."""
    greedy = [
        _entrant(drug_id=9, entry_year=1, share=0.5, ramp=1),
        _entrant(drug_id=10, entry_year=1, share=0.5, ramp=1),
    ]
    result = project_landscape(BASELINE, greedy, horizon_years=3)
    occupied = result.baseline_shares[9][0] + result.baseline_shares[10][0]
    assert occupied == pytest.approx(MAX_ENTRANT_TOTAL_SHARE)
    assert "ENTRANT_SHARE_CAPPED" in {w.code for w in result.warnings}


def test_an_entrant_already_in_the_baseline_is_refused() -> None:
    """It would be written twice — once rescaled as an incumbent and once as
    an entrant — and the year would sum past 1.0."""
    with pytest.raises(DisplacementError):
        project_landscape(BASELINE, [_entrant(drug_id=1)], horizon_years=3)


def test_a_short_baseline_vector_repeats_its_last_year() -> None:
    """A caller supplying one year for a three-year horizon means a constant
    mix, not a mix that runs out."""
    result = project_landscape({1: (0.6,), 2: (0.4,)}, [_entrant()], horizon_years=3)
    for year in range(3):
        assert sum(v[year] for v in result.baseline_shares.values()) == pytest.approx(1.0)
