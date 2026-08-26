"""Unit tests for biet_engine.outcomes — M16 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import EventClass, ResponseThreshold
from biet_engine.exceptions import CurrencyMismatchError
from biet_engine.models import Money, ResponseProfile, TreatmentEffect
from biet_engine.outcomes import (
    effect_retained,
    offset_per_patient,
    project_outcomes,
)

from ..conftest import make_valued

TREATED = (10_000.0, 20_000.0, 30_000.0)


def _effect(
    *, event: EventClass = EventClass.MACE, baseline: float = 0.03,
    reduction: float = 0.20, cost: float = 25_000.0, currency: str = "USD",
    follow_up: int | None = None,
) -> TreatmentEffect:
    return TreatmentEffect(
        drug_id=1, event=event, baseline_rate=make_valued(baseline),
        relative_reduction=make_valued(reduction),
        unit_cost=Money(amount=cost, currency=currency),
        trial="SELECT (NCT03574597)", follow_up_weeks=follow_up,
    )


def _profile(*, share: float = 0.86, regain: float = 0.0) -> ResponseProfile:
    return ResponseProfile(
        drug_id=1, threshold=ResponseThreshold.WL_5,
        responder_share=make_valued(share),
        mean_weight_loss_pct=make_valued(0.149),
        regain_per_year=make_valued(regain),
        trial="STEP 1 (NCT03548935)",
    )


def _run(effects=None, profile=None, persistence: float = 1.0):
    return project_outcomes(
        TREATED, effects if effects is not None else [_effect()], profile,
        persistence=persistence, country_code="USA", currency="USD",
    )


# --------------------------------------------------------------------------- regain


def test_effect_is_full_in_year_one() -> None:
    """A trial's reported effect is the year-one effect. Decaying it in the
    year it was measured double-counts regain the trial already saw."""
    assert effect_retained(1, 0.20) == pytest.approx(1.0)


def test_regain_compounds_from_year_two() -> None:
    assert effect_retained(2, 0.20) == pytest.approx(0.80)
    assert effect_retained(3, 0.20) == pytest.approx(0.64)


def test_zero_regain_holds_the_effect_flat() -> None:
    for year in (1, 2, 3, 5):
        assert effect_retained(year, 0.0) == 1.0


# --------------------------------------------------------------------------- avoided events


def test_avoided_events_are_exposed_times_baseline_times_reduction() -> None:
    """Hand-computed: 10,000 x 0.03 x 0.20 = 60 events avoided in year 1."""
    result = _run()
    year_one = next(a for a in result.avoided if a.year == 1)
    assert year_one.events_without == pytest.approx(300.0)
    assert year_one.avoided == pytest.approx(60.0)
    assert year_one.events_with == pytest.approx(240.0)


def test_cost_avoided_is_events_times_unit_cost() -> None:
    """60 events x $25,000 = $1.5m avoided in year 1."""
    result = _run()
    assert result.total_cost_avoided[0].amount == pytest.approx(1_500_000.0)


def test_persistence_scales_exposure_not_headline_uptake() -> None:
    """An effect accrues only while a patient is on therapy."""
    full = _run(persistence=1.0)
    half = _run(persistence=0.5)
    assert half.total_cost_avoided[0].amount == pytest.approx(
        full.total_cost_avoided[0].amount * 0.5,
    )


def test_zero_persistence_avoids_nothing() -> None:
    result = _run(persistence=0.0)
    assert all(a.avoided == 0.0 for a in result.avoided)
    assert result.total_cost_avoided[0].amount == 0.0


def test_regain_reduces_avoided_events_in_later_years() -> None:
    result = _run(profile=_profile(regain=0.20))
    by_year = {a.year: a.avoided for a in result.avoided}
    # Year 2 has twice the patients but 80% of the effect.
    assert by_year[2] == pytest.approx(20_000.0 * 0.03 * 0.20 * 0.80)


def test_several_event_classes_accumulate_into_one_cost() -> None:
    result = _run(effects=[
        _effect(event=EventClass.MACE, baseline=0.03, reduction=0.20, cost=25_000.0),
        _effect(event=EventClass.INCIDENT_T2D, baseline=0.06, reduction=0.50, cost=9_000.0),
    ])
    mace = 10_000 * 0.03 * 0.20 * 25_000
    t2d = 10_000 * 0.06 * 0.50 * 9_000
    assert result.total_cost_avoided[0].amount == pytest.approx(mace + t2d)


# --------------------------------------------------------------------------- evidence gating


def test_no_supplied_effect_states_the_absence() -> None:
    """Zero avoided events and no evidence about avoided events are different
    claims, and the module keeps them apart (M16 section 5.1)."""
    result = _run(effects=[])
    assert result.avoided == ()
    assert "NO_OUTCOME_EVIDENCE" in {w.code for w in result.warnings}


def test_no_response_profile_gives_none_not_zero() -> None:
    result = _run(profile=None)
    assert result.responders is None
    assert result.mean_weight_loss_pct is None


def test_every_avoided_event_names_its_trial() -> None:
    """A reader disputing the number needs to know which evidence to dispute."""
    for entry in _run().avoided:
        assert entry.trial.strip()


def test_extrapolating_past_the_trial_says_so() -> None:
    result = _run(effects=[_effect(follow_up=104)])   # 2 years, 3-year horizon
    assert "EFFECT_BEYOND_FOLLOW_UP" in {w.code for w in result.warnings}


def test_a_horizon_inside_follow_up_does_not_warn() -> None:
    result = _run(effects=[_effect(follow_up=260)])   # 5 years, 3-year horizon
    assert "EFFECT_BEYOND_FOLLOW_UP" not in {w.code for w in result.warnings}


# --------------------------------------------------------------------------- responders


def test_responders_reflect_persistence() -> None:
    result = _run(profile=_profile(share=0.86), persistence=0.65)
    assert result.responders is not None
    assert result.responders[0] == pytest.approx(10_000 * 0.65 * 0.86)


# --------------------------------------------------------------------------- guards


def test_a_reduction_of_one_is_rejected() -> None:
    """No trial establishes total prevention."""
    with pytest.raises(ValueError, match="total prevention"):
        _effect(reduction=1.0)


def test_a_baseline_rate_above_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="annual probability"):
        _effect(baseline=1.4)


def test_a_unit_cost_in_the_wrong_currency_raises() -> None:
    with pytest.raises(CurrencyMismatchError):
        _run(effects=[_effect(currency="EUR")])


# --------------------------------------------------------------------------- offset


def test_offset_averages_across_the_horizon_not_the_best_year() -> None:
    """M5 carries one offset figure and the effect decays. Taking year 1 would
    credit the therapy with its best year for every year."""
    result = _run(profile=_profile(regain=0.30))
    offset = offset_per_patient(result, TREATED)

    total = sum(m.amount for m in result.total_cost_avoided)
    assert offset.amount == pytest.approx(total / sum(TREATED))
    year_one_rate = result.total_cost_avoided[0].amount / TREATED[0]
    assert offset.amount < year_one_rate


def test_offset_with_no_treated_patients_is_zero_not_undefined() -> None:
    result = project_outcomes(
        (0.0, 0.0), [_effect()], None,
        persistence=1.0, country_code="USA", currency="USD",
    )
    assert offset_per_patient(result, (0.0, 0.0)).amount == 0.0
