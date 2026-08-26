"""Unit tests for biet_engine.impact — M7 section 10."""

from __future__ import annotations

import pytest

from biet_engine.exceptions import MissingFxRateError
from biet_engine.impact import compute_budget_impact
from biet_engine.models import CountryInput, Substitution

from ..conftest import (
    make_country_input,
    make_criterion,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _golden_country() -> CountryInput:
    # admins_per_year=1 so compute_therapy_cost's AC == unit_price exactly,
    # matching the module doc's AC(n)=4800 / AC(t)=1200 worked example.
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=4800.0, currency="EUR",
                                      admins_per_year=1.0)
    # persistence_fraction(0.50) = 0.7213 (M6 reference table, "incretin class default")
    new_therapy = new_therapy.model_copy(update={"persistence_12m": make_valued(0.50)})

    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=1200.0, currency="EUR",
                                     admins_per_year=1.0)
    # persistence_fraction(0.70) = 0.8411 ("oral antidiabetic default")
    comparator = comparator.model_copy(update={"persistence_12m": make_valued(0.70)})

    return make_country_input(
        country_code="DEU", currency="EUR",
        population_total=83_500_000, adult_share=0.820, prevalence=0.2064,
        diagnosis_rate=0.600, treatment_rate=0.150, access_rate=0.700,
        criteria=(make_criterion("synthetic_stack", 0.350),),
        horizon=1, therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )


def test_golden_case_budget_impact() -> None:
    inputs = make_engine_input(
        countries=(_golden_country(),), horizon_years=1, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05,)),
    )

    result = compute_budget_impact(inputs)
    year_1 = result.countries[0].years[0]

    assert year_1.addressable == pytest.approx(311_615, abs=1.0)
    assert year_1.patients_on_new == pytest.approx(15_580.75, abs=0.5)

    # The module doc's own worked example computes net_cost_per_switch from
    # the 4-decimal-place *rounded* persistence fractions in the M6 reference
    # table (0.7213, 0.8411) — 2,452.92. This implementation calls
    # persistence_fraction() itself and carries its full-precision output
    # (0.7213475204444817, 0.8411019756171387) all the way through, per
    # section 5.7's "never round intermediate results" — which the module
    # doc's own worked example doesn't quite follow, being a hand
    # calculation. The ~EUR 0.23 / ~EUR 3,500 differences below are exactly
    # that rounding, not a defect; asserting the tightly-toleranced
    # full-precision value is the correct test for this implementation.
    assert year_1.net_cost_per_switch.amount == pytest.approx(2453.145727392946, abs=1e-6)
    assert year_1.budget_impact.amount == pytest.approx(38_218_333, rel=1e-3)


def test_zero_uptake_every_year_yields_zero_impact() -> None:
    country = make_country_input(horizon=2)
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, uptake=make_uptake_input(vector=(0.0, 0.0)),
    )
    result = compute_budget_impact(inputs)
    for year in result.countries[0].years:
        assert year.budget_impact.amount == pytest.approx(0.0)


def test_new_therapy_cheaper_than_incumbent_yields_negative_impact() -> None:
    cheap_new = make_therapy_input(drug_id=2, is_new=True, unit_price=10.0, currency="USD")
    expensive_comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=1000.0,
                                               currency="USD")
    country = make_country_input(
        currency="USD", horizon=1, therapies=(expensive_comparator,), new_therapy=cheap_new,
        baseline_shares={1: (1.0,)}, substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.5,)),
    )
    result = compute_budget_impact(inputs)
    assert result.countries[0].years[0].budget_impact.amount < 0


def test_no_patients_on_new_yields_none_impact_per_patient() -> None:
    country = make_country_input(horizon=1)
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, uptake=make_uptake_input(vector=(0.0,)),
    )
    result = compute_budget_impact(inputs)
    assert result.countries[0].years[0].impact_per_patient is None


def test_new_therapy_in_comparator_set_raises() -> None:
    dupe = make_therapy_input(drug_id=2, is_new=False)
    new_therapy = make_therapy_input(drug_id=2, is_new=True)
    country = make_country_input(
        horizon=1, therapies=(dupe,), new_therapy=new_therapy,
        baseline_shares={2: (1.0,)}, substitution=Substitution(shares={2: make_valued(1.0)}),
    )
    inputs = make_engine_input(countries=(country,), horizon_years=1)
    with pytest.raises(ValueError, match="comparator set"):
        compute_budget_impact(inputs)


def test_baseline_share_without_matching_therapy_raises() -> None:
    comparator = make_therapy_input(drug_id=1, is_new=False)
    new_therapy = make_therapy_input(drug_id=2, is_new=True)
    country = make_country_input(
        horizon=1, therapies=(comparator,), new_therapy=new_therapy,
        baseline_shares={1: (0.5,), 99: (0.5,)},   # drug_id 99 has no TherapyInput
        substitution=Substitution(shares={1: make_valued(0.5), 99: make_valued(0.5)}),
    )
    inputs = make_engine_input(countries=(country,), horizon_years=1)
    with pytest.raises(ValueError, match="no matching therapy"):
        compute_budget_impact(inputs)


def test_missing_fx_rate_raises() -> None:
    country = make_country_input(currency="JPY", horizon=1)
    inputs = make_engine_input(countries=(country,), horizon_years=1,
                                fx_rates={"USD": 1.0})       # no JPY rate
    with pytest.raises(MissingFxRateError):
        compute_budget_impact(inputs)


def test_missing_reporting_currency_fx_rate_raises() -> None:
    country = make_country_input(currency="EUR", horizon=1)
    inputs = make_engine_input(countries=(country,), horizon_years=1,
                                reporting_currency="GBP",
                                fx_rates={"EUR": 0.86386})   # no GBP rate
    with pytest.raises(MissingFxRateError):
        compute_budget_impact(inputs)


def test_currency_conversion_deu_to_usd_is_exact_and_reversible() -> None:
    country = make_country_input(currency="EUR", horizon=1)
    fx_rates = {"EUR": 0.86386, "USD": 1.0}
    inputs = make_engine_input(countries=(country,), horizon_years=1,
                                reporting_currency="USD", fx_rates=fx_rates)
    result = compute_budget_impact(inputs)

    local = result.countries[0].years[0].budget_impact
    expected_usd = (local.amount / fx_rates["EUR"]) * fx_rates["USD"]
    assert result.totals.by_year[0].amount == pytest.approx(expected_usd, rel=1e-9)

    back_to_eur = (expected_usd / fx_rates["USD"]) * fx_rates["EUR"]
    assert back_to_eur == pytest.approx(local.amount, rel=1e-9)


def test_peak_year_ties_resolve_to_earliest() -> None:
    country = make_country_input(horizon=3)
    # Identical uptake in years 1 and 3, lower in year 2 -> tied peak, earliest wins.
    inputs = make_engine_input(
        countries=(country,), horizon_years=3,
        uptake=make_uptake_input(vector=(0.10, 0.02, 0.10), allow_erosion=True),
    )
    result = compute_budget_impact(inputs)
    assert result.totals.peak_year == 1


def test_horizon_one_cumulative_equals_year_one() -> None:
    country = make_country_input(horizon=1)
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, uptake=make_uptake_input(vector=(0.05,)),
    )
    result = compute_budget_impact(inputs)
    assert result.countries[0].cumulative_budget_impact.amount == pytest.approx(
        result.countries[0].years[0].budget_impact.amount
    )


# --------------------------------------------------------- the two worlds


def test_totals_carry_both_worlds_and_their_difference_is_the_impact() -> None:
    """`with - without = impact` must survive aggregation exactly.

    All three convert through the same FX snapshot, so the identity that
    holds per market per year holds after summing across markets. A reader
    asked to fund an increment will ask what it is an increment over, and a
    total that does not reconcile to its own two worlds is not defensible.
    """
    inputs = make_engine_input(
        countries=(_golden_country(),), horizon_years=1, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05,)),
    )

    totals = compute_budget_impact(inputs).totals

    assert len(totals.without_by_year) == len(totals.by_year) == 1
    assert totals.with_by_year[0].amount - totals.without_by_year[0].amount == pytest.approx(
        totals.by_year[0].amount, rel=1e-9
    )


def test_both_worlds_are_reported_in_the_reporting_currency() -> None:
    """Not in the market's own currency — these are cross-market sums."""
    inputs = make_engine_input(
        countries=(_golden_country(),), horizon_years=1, reporting_currency="USD",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.05,)),
    )

    totals = compute_budget_impact(inputs).totals

    assert totals.without_by_year[0].currency == "USD"
    assert totals.with_by_year[0].currency == "USD"


def test_zero_uptake_leaves_the_two_worlds_identical() -> None:
    """Nothing switches, so the world with the asset is the world without it —
    and the increment is zero because the two worlds coincide, not because a
    subtraction happened to cancel."""
    inputs = make_engine_input(
        countries=(_golden_country(),), horizon_years=1, reporting_currency="EUR",
        fx_rates={"EUR": 1.0, "USD": 0.86386},
        uptake=make_uptake_input(vector=(0.0,)),
    )

    totals = compute_budget_impact(inputs).totals

    assert totals.with_by_year[0].amount == pytest.approx(totals.without_by_year[0].amount)
    assert totals.by_year[0].amount == pytest.approx(0.0, abs=1e-6)


def test_the_world_without_the_asset_does_not_move_with_uptake() -> None:
    """Uptake changes what the payer spends, not what they would have spent."""
    def totals_at(uptake: float):
        return compute_budget_impact(
            make_engine_input(
                countries=(_golden_country(),), horizon_years=1, reporting_currency="EUR",
                fx_rates={"EUR": 1.0, "USD": 0.86386},
                uptake=make_uptake_input(vector=(uptake,)),
            )
        ).totals

    low, high = totals_at(0.05), totals_at(0.40)

    assert low.without_by_year[0].amount == pytest.approx(high.without_by_year[0].amount)
    assert high.with_by_year[0].amount > low.with_by_year[0].amount
