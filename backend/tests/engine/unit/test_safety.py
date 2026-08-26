"""Unit tests for biet_engine.safety — M13 section 10."""

from __future__ import annotations

import pytest

from biet_engine.constants import CostComponent
from biet_engine.cost import compute_therapy_cost
from biet_engine.exceptions import CurrencyMismatchError
from biet_engine.models import (
    AdverseEvent,
    EventIncidence,
    Money,
    SafetyProfile,
)
from biet_engine.safety import annualise, build_cost_bridge, expected_ae_cost

from ..conftest import make_therapy_input, make_valued

NAUSEA = AdverseEvent(code="nausea", label="Nausea")
SEVERE = AdverseEvent(code="severe_event", label="Severe event", is_serious=True)


def _profile(*events: EventIncidence, drug_id: int = 1) -> SafetyProfile:
    return SafetyProfile(drug_id=drug_id, country_code="USA", events=events)


def _event(
    incidence: float, cost: float, weeks: int | None = None,
    event: AdverseEvent = NAUSEA, currency: str = "USD",
) -> EventIncidence:
    return EventIncidence(
        event=event, incidence=make_valued(incidence), exposure_weeks=weeks,
        unit_cost=Money(amount=cost, currency=currency),
    )


# --------------------------------------------------------------------------- annualisation


def test_annualise_is_the_identity_at_a_full_year() -> None:
    assert annualise(0.20, 52) == pytest.approx(0.20)


def test_annualise_is_skipped_when_the_source_reports_an_annual_rate() -> None:
    """None means "already annual". Converting again would double-count."""
    assert annualise(0.20, None) == pytest.approx(0.20)


def test_a_longer_window_annualises_downward() -> None:
    """A 68-week trial incidence quoted as an annual rate overstates it —
    the patient was exposed for longer than a year."""
    assert annualise(0.20, 68) == pytest.approx(0.1569, abs=1e-4)
    assert annualise(0.20, 68) < 0.20


def test_a_shorter_window_annualises_upward() -> None:
    assert annualise(0.20, 26) == pytest.approx(0.36, abs=1e-4)
    assert annualise(0.20, 26) > 0.20


def test_certainty_stays_certain_at_any_window() -> None:
    """No extrapolation beyond "every patient" is available, so 1.0 cannot
    inflate past 1.0 however short the observation window."""
    for weeks in (4, 26, 68, 104):
        assert annualise(1.0, weeks) == 1.0


def test_zero_incidence_annualises_to_zero() -> None:
    assert annualise(0.0, 26) == 0.0


def test_annualised_incidence_never_leaves_the_unit_interval() -> None:
    for incidence in (0.01, 0.5, 0.99):
        for weeks in (1, 4, 26, 52, 104, 260):
            assert 0.0 <= annualise(incidence, weeks) <= 1.0


# --------------------------------------------------------------------------- expected cost


def test_expected_cost_is_the_sum_of_incidence_times_unit_cost() -> None:
    """Hand-computed: 0.40 x 100 + 0.02 x 2000 = 40 + 40 = 80."""
    profile = _profile(
        _event(0.40, 100.0),
        _event(0.02, 2000.0, event=SEVERE),
    )
    assert expected_ae_cost(profile, "USD").amount == pytest.approx(80.0)


def test_expected_cost_annualises_before_summing() -> None:
    profile = _profile(_event(0.20, 100.0, weeks=68))
    assert expected_ae_cost(profile, "USD").amount == pytest.approx(15.69, abs=1e-2)


def test_an_empty_profile_costs_zero() -> None:
    """A real answer, and distinct from "this therapy has no profile" — which
    is a state the caller holds, not this function."""
    assert expected_ae_cost(_profile(), "USD").amount == 0.0


def test_a_unit_cost_in_the_wrong_currency_raises() -> None:
    """Two currencies summed into one number produce something plausible and
    wrong, which is the failure mode this system exists to prevent."""
    profile = _profile(_event(0.4, 100.0, currency="EUR"))
    with pytest.raises(CurrencyMismatchError):
        expected_ae_cost(profile, "USD")


def test_expected_cost_carries_the_market_currency() -> None:
    assert expected_ae_cost(_profile(_event(0.1, 10.0)), "USD").currency == "USD"


# --------------------------------------------------------------------------- the bridge


def _bridge(
    *, new_price: float = 200.0, comparator_price: float = 100.0,
    new_ae: float = 50.0, comparator_ae: float = 400.0,
    new_persistence: float = 1.0, comparator_persistence: float = 1.0,
):
    new = compute_therapy_cost(
        make_therapy_input(
            drug_id=1, unit_price=new_price, admins_per_year=1.0, ae_cost=new_ae,
        ), "USA",
    )
    comparator = compute_therapy_cost(
        make_therapy_input(
            drug_id=2, is_new=False, unit_price=comparator_price,
            admins_per_year=1.0, ae_cost=comparator_ae,
        ), "USA",
    )
    return build_cost_bridge(
        new, [comparator],
        substitution={2: 1.0},
        persistence={1: new_persistence, 2: comparator_persistence},
        country_code="USA",
    )


def test_bridge_terms_sum_to_the_net_cost_per_switch() -> None:
    bridge = _bridge()
    total = sum(
        -t.delta.amount if t.component is CostComponent.OFFSET else t.delta.amount
        for t in bridge.terms
    )
    assert total == pytest.approx(bridge.net_cost_per_switch.amount)


def test_bridge_covers_every_cost_component_exactly_once() -> None:
    """The decomposition is only exact if it covers all of them and nothing
    else — a missing component would silently absorb into no term at all."""
    components = [t.component for t in _bridge().terms]
    assert components == list(CostComponent)


def test_a_dearer_therapy_with_better_safety_can_still_cost_less() -> None:
    """The point of the module. Acquisition is +100 and adverse events are
    -350, so the net is a saving even though the headline price is higher."""
    bridge = _bridge(new_price=200.0, comparator_price=100.0,
                     new_ae=50.0, comparator_ae=400.0)
    by = {t.component: t.delta.amount for t in bridge.terms}
    assert by[CostComponent.ACQUISITION] == pytest.approx(100.0)
    assert by[CostComponent.AE] == pytest.approx(-350.0)
    assert bridge.net_cost_per_switch.amount == pytest.approx(-250.0)


def test_the_offset_enters_negatively() -> None:
    """An offset is an avoided cost. Getting its sign wrong would make a
    saving read as an extra cost."""
    new = compute_therapy_cost(
        make_therapy_input(drug_id=1, unit_price=100.0, admins_per_year=1.0, offset=60.0),
        "USA",
    )
    comparator = compute_therapy_cost(
        make_therapy_input(
            drug_id=2, is_new=False, unit_price=100.0, admins_per_year=1.0, offset=0.0,
        ),
        "USA",
    )
    bridge = build_cost_bridge(
        new, [comparator], substitution={2: 1.0}, persistence={1: 1.0, 2: 1.0},
        country_code="USA",
    )
    # Same acquisition on both sides, so the whole net is the offset — and it
    # must be a saving.
    assert bridge.net_cost_per_switch.amount == pytest.approx(-60.0)


def test_persistence_scales_both_sides_of_every_term() -> None:
    full = _bridge(new_persistence=1.0, comparator_persistence=1.0)
    half = _bridge(new_persistence=0.5, comparator_persistence=0.5)
    assert half.net_cost_per_switch.amount == pytest.approx(
        full.net_cost_per_switch.amount * 0.5,
    )


def test_a_wholly_treatment_naive_substitution_leaves_the_full_cost() -> None:
    """Nothing is displaced, so the displaced side of every term is zero and
    the net is the new therapy's entire cost."""
    new = compute_therapy_cost(
        make_therapy_input(drug_id=1, unit_price=200.0, admins_per_year=1.0), "USA",
    )
    comparator = compute_therapy_cost(
        make_therapy_input(
            drug_id=2, is_new=False, unit_price=100.0, admins_per_year=1.0,
        ),
        "USA",
    )
    bridge = build_cost_bridge(
        new, [comparator],
        substitution={},                       # every switcher was untreated
        persistence={1: 1.0, 2: 1.0}, country_code="USA",
    )
    assert bridge.net_cost_per_switch.amount == pytest.approx(200.0)
    assert all(t.displaced.amount == 0.0 for t in bridge.terms)


def test_a_comparator_in_another_currency_raises() -> None:
    new = compute_therapy_cost(
        make_therapy_input(drug_id=1, unit_price=100.0, currency="USD"), "USA",
    )
    comparator = compute_therapy_cost(
        make_therapy_input(drug_id=2, is_new=False, unit_price=100.0, currency="EUR"),
        "USA",
    )
    with pytest.raises(CurrencyMismatchError):
        build_cost_bridge(
            new, [comparator], substitution={2: 1.0}, persistence={1: 1.0, 2: 1.0},
            country_code="USA",
        )
