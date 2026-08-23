"""Unit tests for biet_engine.uptake — M4 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import UptakeCurve
from biet_engine.exceptions import (
    DisplacementError,
    UnknownTherapyError,
    UptakeMonotonicityError,
)
from biet_engine.models import Substitution, UptakeInput
from biet_engine.uptake import build_market_mix, displace, project_uptake

from ..conftest import make_valued


def test_linear_uptake() -> None:
    inputs = UptakeInput(curve=UptakeCurve.LINEAR, year_1=make_valued(0.05), terminal=make_valued(0.15))
    result = project_uptake(inputs, horizon=3)
    assert result == pytest.approx((0.05, 0.10, 0.15))


def test_linear_uptake_horizon_one() -> None:
    inputs = UptakeInput(curve=UptakeCurve.LINEAR, year_1=make_valued(0.05), terminal=make_valued(0.15))
    result = project_uptake(inputs, horizon=1)
    assert result == pytest.approx((0.05,))


def test_logistic_uptake() -> None:
    inputs = UptakeInput(
        curve=UptakeCurve.LOGISTIC, terminal=make_valued(0.15),
        steepness=make_valued(1.2), inflection_year=make_valued(1.5),
    )
    result = project_uptake(inputs, horizon=3)
    assert result[0] == pytest.approx(0.0532, abs=1e-4)
    assert result[2] == pytest.approx(0.1287, abs=1e-4)


def test_logistic_uses_default_steepness_and_inflection() -> None:
    # Same defaults (k=1.2, y_mid=N/2=1.5) reached without supplying them.
    inputs = UptakeInput(curve=UptakeCurve.LOGISTIC, terminal=make_valued(0.15))
    result = project_uptake(inputs, horizon=3)
    assert result[0] == pytest.approx(0.0532, abs=1e-4)
    assert result[2] == pytest.approx(0.1287, abs=1e-4)


def test_manual_uptake_passes_through_unchanged() -> None:
    inputs = UptakeInput(curve=UptakeCurve.MANUAL, vector=(0.02, 0.08, 0.20))
    result = project_uptake(inputs, horizon=3)
    assert result == (0.02, 0.08, 0.20)


def test_manual_vector_wrong_length_raises() -> None:
    inputs = UptakeInput(curve=UptakeCurve.MANUAL, vector=(0.02, 0.08))
    with pytest.raises(ValueError, match="horizon"):
        project_uptake(inputs, horizon=3)


def test_manual_missing_vector_raises() -> None:
    inputs = UptakeInput(curve=UptakeCurve.MANUAL)
    with pytest.raises(ValueError, match="vector"):
        project_uptake(inputs, horizon=3)


def test_linear_missing_parameters_raises() -> None:
    inputs = UptakeInput(curve=UptakeCurve.LINEAR)
    with pytest.raises(ValueError, match="year_1 and terminal"):
        project_uptake(inputs, horizon=3)


def test_logistic_missing_terminal_raises() -> None:
    inputs = UptakeInput(curve=UptakeCurve.LOGISTIC)
    with pytest.raises(ValueError, match="terminal"):
        project_uptake(inputs, horizon=3)


def test_uptake_outside_unit_interval_raises() -> None:
    inputs = UptakeInput(curve=UptakeCurve.MANUAL, vector=(1.5, 0.5, 0.5))
    with pytest.raises(ValueError, match="outside \\[0, 1\\]"):
        project_uptake(inputs, horizon=3)


def test_decreasing_vector_raises_without_allow_erosion() -> None:
    inputs = UptakeInput(curve=UptakeCurve.MANUAL, vector=(0.20, 0.10, 0.30))
    with pytest.raises(UptakeMonotonicityError):
        project_uptake(inputs, horizon=3)


def test_decreasing_vector_passes_with_allow_erosion() -> None:
    inputs = UptakeInput(
        curve=UptakeCurve.MANUAL, vector=(0.20, 0.10, 0.30), allow_erosion=True,
    )
    result = project_uptake(inputs, horizon=3)
    assert result == (0.20, 0.10, 0.30)


def test_displacement_below_floor() -> None:
    m_with, redistributed = displace({1: 0.40}, u=0.05, sigma={1: 0.60})
    assert m_with[1] == pytest.approx(0.370)
    assert redistributed is False


def test_displacement_floor_binds_and_redistributes() -> None:
    m_with, redistributed = displace(
        {1: 0.01, 2: 0.50}, u=0.05, sigma={1: 0.60, 2: 0.40}
    )
    assert m_with[1] == 0.0
    assert redistributed is True
    # deficit = 0.03 - 0.01 = 0.02, drawn entirely from drug 2 (only headroom)
    assert m_with[2] == pytest.approx(0.50 - 0.02 - 0.05 * 0.40)


def test_displacement_no_headroom_raises() -> None:
    with pytest.raises(DisplacementError):
        displace({1: 0.01, 2: 0.0}, u=0.05, sigma={1: 0.60, 2: 0.40})


def test_substitution_shares_summing_to_less_than_one_raises() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        Substitution(shares={1: make_valued(0.60), 2: make_valued(0.39)})


def test_substitution_shares_negative_raises() -> None:
    with pytest.raises(ValueError, match="negative"):
        Substitution(shares={1: make_valued(1.1), 2: make_valued(-0.1)})


def test_build_market_mix_share_accounting() -> None:
    baseline = {1: [0.40, 0.40], 2: [0.60, 0.60]}
    substitution = Substitution(shares={1: make_valued(0.60), 2: make_valued(0.40)})
    mixes = build_market_mix(baseline, uptake=[0.05, 0.10], substitution=substitution,
                              country_code="DEU")

    assert len(mixes) == 2
    for mix in mixes:
        assert mix.uptake + sum(mix.shares_with.values()) == pytest.approx(1.0, abs=1e-9)


def test_build_market_mix_emits_substitution_floor_warning() -> None:
    baseline = {1: [0.01], 2: [0.99]}
    substitution = Substitution(shares={1: make_valued(0.60), 2: make_valued(0.40)})
    mixes = build_market_mix(baseline, uptake=[0.05], substitution=substitution,
                              country_code="DEU")
    assert len(mixes[0].warnings) == 1
    assert mixes[0].warnings[0].code == "SUBSTITUTION_FLOOR"


def test_build_market_mix_unknown_therapy_raises() -> None:
    baseline = {1: [1.0]}
    substitution = Substitution(shares={1: make_valued(0.5), 2: make_valued(0.5)})
    with pytest.raises(UnknownTherapyError):
        build_market_mix(baseline, uptake=[0.05], substitution=substitution,
                          country_code="DEU")


def test_build_market_mix_baseline_not_summing_to_one_raises() -> None:
    baseline = {1: [0.40], 2: [0.50]}
    substitution = Substitution(shares={1: make_valued(0.6), 2: make_valued(0.4)})
    with pytest.raises(ValueError, match="baseline shares"):
        build_market_mix(baseline, uptake=[0.05], substitution=substitution,
                          country_code="DEU")
