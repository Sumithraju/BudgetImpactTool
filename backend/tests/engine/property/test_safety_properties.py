"""Property tests for biet_engine.safety — M13 section 10, "Property" class.

The bridge's terms sum to its total "exactly by construction". That is a claim
about code, and code changes, so it is asserted over random inputs rather than
trusted.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from biet_engine.constants import CostComponent
from biet_engine.cost import compute_therapy_cost
from biet_engine.safety import annualise, build_cost_bridge

from ..conftest import make_therapy_input

_money = st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_rate = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)


@given(
    new_price=st.floats(min_value=0.01, max_value=5_000.0),
    comparator_price=st.floats(min_value=0.01, max_value=5_000.0),
    new_ae=_money, comparator_ae=_money,
    new_admin=_money, comparator_monitoring=_money,
    new_offset=_money,
    sigma=st.floats(min_value=0.0, max_value=1.0),
    f_new=_rate, f_comparator=_rate,
)
def test_bridge_terms_always_sum_to_the_net(
    new_price: float, comparator_price: float, new_ae: float, comparator_ae: float,
    new_admin: float, comparator_monitoring: float, new_offset: float,
    sigma: float, f_new: float, f_comparator: float,
) -> None:
    new = compute_therapy_cost(
        make_therapy_input(
            drug_id=1, unit_price=new_price, admins_per_year=1.0,
            ae_cost=new_ae, admin_cost=new_admin, offset=new_offset,
        ), "USA",
    )
    comparator = compute_therapy_cost(
        make_therapy_input(
            drug_id=2, is_new=False, unit_price=comparator_price, admins_per_year=1.0,
            ae_cost=comparator_ae, monitoring_cost=comparator_monitoring,
        ), "USA",
    )
    bridge = build_cost_bridge(
        new, [comparator], substitution={2: sigma},
        persistence={1: f_new, 2: f_comparator}, country_code="USA",
    )

    total = sum(
        -t.delta.amount if t.component is CostComponent.OFFSET else t.delta.amount
        for t in bridge.terms
    )
    assert total == pytest.approx(bridge.net_cost_per_switch.amount, rel=1e-9, abs=1e-9)


@given(
    base_ae=st.floats(min_value=0.0, max_value=0.5),
    extra=st.floats(min_value=0.0, max_value=0.4),
    unit_cost=st.floats(min_value=1.0, max_value=5_000.0),
)
def test_a_worse_ae_profile_never_lowers_the_net_cost(
    base_ae: float, extra: float, unit_cost: float,
) -> None:
    """Monotonicity. Raising only the new therapy's adverse-event cost cannot
    make it cheaper — if it could, a safety disadvantage would read as a
    saving."""
    def net(ae_incidence: float) -> float:
        new = compute_therapy_cost(
            make_therapy_input(
                drug_id=1, unit_price=100.0, admins_per_year=1.0,
                ae_cost=ae_incidence * unit_cost,
            ), "USA",
        )
        comparator = compute_therapy_cost(
            make_therapy_input(
                drug_id=2, is_new=False, unit_price=100.0, admins_per_year=1.0,
            ), "USA",
        )
        return build_cost_bridge(
            new, [comparator], substitution={2: 1.0}, persistence={1: 1.0, 2: 1.0},
            country_code="USA",
        ).net_cost_per_switch.amount

    assert net(base_ae + extra) >= net(base_ae) - 1e-9


@given(
    incidence=st.floats(min_value=0.0, max_value=1.0),
    weeks=st.integers(min_value=1, max_value=520),
)
def test_annualised_incidence_stays_a_probability(incidence: float, weeks: int) -> None:
    """Whatever the window, the result is still a fraction of patients."""
    assert 0.0 <= annualise(incidence, weeks) <= 1.0


@given(
    incidence=st.floats(min_value=0.001, max_value=0.999),
    weeks=st.integers(min_value=1, max_value=520),
)
def test_annualisation_direction_follows_the_window(
    incidence: float, weeks: int,
) -> None:
    """Longer than a year annualises down, shorter annualises up, and exactly
    a year does neither. Getting the direction backwards would be invisible
    in any single number and wrong in all of them."""
    annual = annualise(incidence, weeks)
    if weeks > 52:
        assert annual <= incidence + 1e-12
    elif weeks < 52:
        assert annual >= incidence - 1e-12
    else:
        assert annual == pytest.approx(incidence)
