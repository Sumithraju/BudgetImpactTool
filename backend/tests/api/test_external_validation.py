"""Validation against published figures, not just internal consistency.

Every other test in this suite checks that the system agrees with itself.
These check that it agrees with the outside world: that a cost the engine
computes reconciles to a price someone actually published.

That distinction matters. A model can be internally immaculate — every
invariant asserted, every branch covered — and still be wrong about the
thing it claims to measure. Nothing else here would catch that.

**Scope, stated honestly.** This is not a reproduction of a published budget
impact model. Doing that faithfully needs another model's complete input set
— its population base, funnel, price assumptions, horizon and offsets — and
the published analyses located for this project report their outputs without
enough of their inputs to replicate. Claiming a match without genuinely
matching assumptions would be an unearned credibility claim. What is
verifiable, and is verified here, is the layer underneath: that annual
therapy cost reconciles exactly to published list prices.
"""

from __future__ import annotations

import pytest

from biet_engine.cost import compute_therapy_cost
from biet_engine.models import (
    ConfidenceTier,
    Money,
    PriceBasis,
    Provenance,
    Regimen,
    ResolutionLevel,
    TherapyInput,
    Valued,
)

#: Published list prices, per package, with the package definition that
#: makes them meaningful. A "monthly" GLP-1 package is 28 days, not a
#: calendar month — which is the detail the first test exists to pin.
WEGOVY_US_PACKAGE_USD = 1349.02          # 4 weekly pens at 2.4 mg = 9.6 mg
WEGOVY_DE_PACKAGE_EUR = 301.91           # same package, German launch price
MOUNJARO_DE_PACKAGE_EUR = 383.00         # 4 weekly pens at 10 mg = 40 mg

WEEKS_PER_YEAR = 52


def _weekly_injectable(
    unit_price: float, currency: str, mg_per_dose: float,
) -> TherapyInput:
    flat = Provenance(
        source="published list price",
        confidence_tier=ConfidenceTier.B,
        resolution_level=ResolutionLevel.COUNTRY_OVERRIDE,
    )
    return TherapyInput(
        drug_id=1, name="validation", is_new=True,
        regimen=Regimen(
            units_per_admin=Valued(value=mg_per_dose, provenance=flat),
            admins_per_year=Valued(value=float(WEEKS_PER_YEAR), provenance=flat),
            wastage_pct=Valued(value=0.0, provenance=flat),
        ),
        unit_price=Money(amount=unit_price, currency=currency),
        price_basis=PriceBasis.LIST,
        price_provenance=flat,
        discount_pct=Valued(value=0.0, provenance=flat),
        admin_cost=Money(amount=0.0, currency=currency),
        monitoring_cost=Money(amount=0.0, currency=currency),
        ae_cost=Money(amount=0.0, currency=currency),
        offset=Money(amount=0.0, currency=currency),
        persistence_12m=Valued(value=1.0, provenance=flat),
    )


def test_us_annual_cost_reconciles_to_thirteen_published_packages() -> None:
    """52 weekly doses is 13 four-week packages, and the engine lands on the
    published package price times thirteen — exactly, not approximately."""
    therapy = _weekly_injectable(
        unit_price=WEGOVY_US_PACKAGE_USD / 9.6,   # published package -> per mg
        currency="USD", mg_per_dose=2.4,
    )
    cost = compute_therapy_cost(therapy, country_code="USA")

    assert cost.acquisition.amount == pytest.approx(
        WEGOVY_US_PACKAGE_USD * 13, rel=1e-9,
    )


def test_the_naive_twelve_month_figure_undercounts_by_four_weeks() -> None:
    """A guard against a mistake that is easy to make and hard to see.

    Quoting a "monthly" price twelve times looks like an annual cost, but a
    28-day package times twelve covers 336 days — four weeks short. The
    engine is 8.3% above that figure, and it is the naive one that is wrong.
    Anyone reconciling this model against a spreadsheet built the other way
    will hit this discrepancy, so it is pinned here with its explanation.
    """
    therapy = _weekly_injectable(
        unit_price=WEGOVY_US_PACKAGE_USD / 9.6, currency="USD", mg_per_dose=2.4,
    )
    engine = compute_therapy_cost(therapy, country_code="USA").acquisition.amount
    naive_twelve_months = WEGOVY_US_PACKAGE_USD * 12

    assert engine > naive_twelve_months
    assert (engine - naive_twelve_months) / naive_twelve_months == pytest.approx(
        1 / 12, rel=1e-6,      # exactly one extra package
    )


@pytest.mark.parametrize(
    "package_price,mg_per_package,mg_per_dose,currency",
    [
        (WEGOVY_US_PACKAGE_USD, 9.6, 2.4, "USD"),
        (WEGOVY_DE_PACKAGE_EUR, 9.6, 2.4, "EUR"),
        (MOUNJARO_DE_PACKAGE_EUR, 40.0, 10.0, "EUR"),
    ],
)
def test_published_package_prices_round_trip_through_the_engine(
    package_price: float, mg_per_package: float, mg_per_dose: float, currency: str,
) -> None:
    """Each seeded price converts package -> per-mg -> annual and back
    without drift, across both currencies and both molecules."""
    therapy = _weekly_injectable(
        unit_price=package_price / mg_per_package,
        currency=currency, mg_per_dose=mg_per_dose,
    )
    annual = compute_therapy_cost(therapy, country_code="XXX").acquisition.amount
    packages_per_year = WEEKS_PER_YEAR / (mg_per_package / mg_per_dose)

    assert annual == pytest.approx(package_price * packages_per_year, rel=1e-9)


def test_german_wegovy_is_materially_cheaper_than_us() -> None:
    """A published, well-documented fact the model must reproduce: European
    list prices for this class sit far below US ones. If this ever inverts,
    a price or a currency has been entered wrongly."""
    us = compute_therapy_cost(
        _weekly_injectable(WEGOVY_US_PACKAGE_USD / 9.6, "USD", 2.4), "USA",
    ).acquisition.amount
    de = compute_therapy_cost(
        _weekly_injectable(WEGOVY_DE_PACKAGE_EUR / 9.6, "EUR", 2.4), "DEU",
    ).acquisition.amount

    # Compared in their own currencies deliberately: the gap is roughly
    # four-fold and no plausible EUR/USD rate closes it, so the assertion
    # holds without depending on an FX snapshot.
    assert de < us / 3
