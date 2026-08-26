"""Unit tests for biet_engine.cost — M5 section 10."""

from __future__ import annotations

import pytest

from biet_engine.cost import compute_therapy_cost, derive_ppp_price
from biet_engine.exceptions import CurrencyMismatchError
from biet_engine.models import Money

from ..conftest import make_therapy_input


def test_acquisition_cost_worked_example() -> None:
    therapy = make_therapy_input(
        unit_price=100.0, units_per_admin=1.0, admins_per_year=12.0,
        wastage_pct=0.05, discount_pct=0.20,
    )
    cost = compute_therapy_cost(therapy, country_code="USA")
    assert cost.acquisition.amount == pytest.approx(1008.00, abs=1e-2)


def test_wastage_and_discount_are_separate_multiplicative_factors() -> None:
    """The formula is price x qty x (1+wastage) x (1-discount) — two separate
    multiplicative terms. The easy-to-write-by-mistake alternative collapses
    them into one additive adjustment, (1 + wastage - discount); for pure
    scalar multiplication the two *sequential* multiplicative orderings are
    identical (multiplication is commutative), so what the module spec's
    "different order gives a different number" is actually guarding against
    is this multiplicative-vs-additive mistake, not a literal reordering."""
    therapy = make_therapy_input(
        unit_price=100.0, units_per_admin=1.0, admins_per_year=12.0,
        wastage_pct=0.05, discount_pct=0.20,
    )
    correct = compute_therapy_cost(therapy, country_code="USA").acquisition.amount

    naive_additive = 100.0 * 1.0 * 12.0 * (1 + 0.05 - 0.20)
    assert correct != pytest.approx(naive_additive)


def test_total_annual_cost_worked_example() -> None:
    therapy = make_therapy_input(
        unit_price=100.0, units_per_admin=1.0, admins_per_year=12.0,
        wastage_pct=0.05, discount_pct=0.20,
        admin_cost=50.0, monitoring_cost=120.0, ae_cost=30.0, offset=200.0,
    )
    cost = compute_therapy_cost(therapy, country_code="USA")
    assert cost.total.amount == pytest.approx(1008.00, abs=1e-2)


def test_negative_offset_raises_value_error() -> None:
    with pytest.raises(ValueError, match="offset"):
        make_therapy_input(offset=-1.0)


def test_negative_total_permitted_when_offset_dominates() -> None:
    therapy = make_therapy_input(unit_price=10.0, units_per_admin=1.0, offset=10_000.0)
    cost = compute_therapy_cost(therapy, country_code="USA")
    assert cost.total.amount < 0


def test_ppp_reference_case() -> None:
    price = derive_ppp_price(
        reference_price=10_000, gdp_pc_ppp_target=29_333, gdp_pc_ppp_reference=90_027,
        elasticity=1.0, floor=0.05,
    )
    assert price == pytest.approx(3258.24, abs=1e-2)


def test_ppp_floor_does_not_bind_at_elasticity_one_for_india() -> None:
    price = derive_ppp_price(
        reference_price=10_000, gdp_pc_ppp_target=11_748, gdp_pc_ppp_reference=90_027,
        elasticity=1.0, floor=0.05,
    )
    assert price == pytest.approx(1304.94, abs=1e-2)
    assert price > 0.05 * 10_000                # floor did not bind


def test_ppp_floor_binds_at_elasticity_two_for_india() -> None:
    unconstrained = 10_000 * (11_748 / 90_027) ** 2
    assert unconstrained == pytest.approx(170.29, abs=1e-2)

    price = derive_ppp_price(
        reference_price=10_000, gdp_pc_ppp_target=11_748, gdp_pc_ppp_reference=90_027,
        elasticity=2.0, floor=0.05,
    )
    assert price == pytest.approx(500.0, abs=1e-2)   # floor x reference_price, not 170.29


def test_ppp_elasticity_zero_yields_reference_price_everywhere() -> None:
    price = derive_ppp_price(
        reference_price=10_000, gdp_pc_ppp_target=11_748, gdp_pc_ppp_reference=90_027,
        elasticity=0.0, floor=0.05,
    )
    assert price == pytest.approx(10_000)


def test_mixed_currency_addition_raises_currency_mismatch() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(amount=10, currency="USD") + Money(amount=10, currency="EUR")


def test_no_pharmacotherapy_yields_total_zero() -> None:
    no_pharma = make_therapy_input(
        unit_price=0.01, units_per_admin=0.0, admins_per_year=1.0,
        admin_cost=0.0, monitoring_cost=0.0, ae_cost=0.0, offset=0.0,
    )
    cost = compute_therapy_cost(no_pharma, country_code="USA")
    assert cost.total.amount == 0.0
