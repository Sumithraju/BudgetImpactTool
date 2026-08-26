"""Unit tests for biet_engine.psa — M9 section 10 (PSA half)."""

from __future__ import annotations

import time

import pytest

from biet_engine.constants import PSA_DEFAULT_SEED, ConfidenceTier
from biet_engine.impact import compute_budget_impact
from biet_engine.models import Substitution, Valued
from biet_engine.psa import run_psa

from ..conftest import (
    make_country_input,
    make_engine_input,
    make_provenance,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _differentiated_country(code: str = "USA", horizon: int = 2, *, zero_variance: bool = False):
    new = make_therapy_input(drug_id=2, is_new=True, unit_price=300.0, currency="USD")
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code=code, currency="USD", horizon=horizon,
        therapies=(comparator,), new_therapy=new,
        baseline_shares={1: (1.0,) * horizon},
        substitution=Substitution(shares={1: make_valued(1.0)}),
    )
    if not zero_variance:
        return country

    # Published low == high everywhere -> zero variance -> every draw must
    # land exactly on the deterministic base case.
    def _pin(v: Valued) -> Valued:
        return v.model_copy(update={"low": v.value, "high": v.value})

    return country.model_copy(update={
        "adult_share": _pin(country.adult_share),
        "prevalence": _pin(country.prevalence),
        "funnel": country.funnel.model_copy(update={
            "diagnosis_rate": _pin(country.funnel.diagnosis_rate),
            "treatment_rate": _pin(country.funnel.treatment_rate),
            "access_rate": _pin(country.funnel.access_rate),
        }),
        "criteria": tuple(
            c.model_copy(update={"factor": _pin(c.factor)}) for c in country.criteria
        ),
        "new_therapy": country.new_therapy.model_copy(update={
            "persistence_12m": _pin(country.new_therapy.persistence_12m),
        }),
        "therapies": tuple(
            t.model_copy(update={"persistence_12m": _pin(t.persistence_12m)})
            for t in country.therapies
        ),
    })


def test_psa_matches_compute_budget_impact_at_zero_variance() -> None:
    """The guard against the two budget-impact implementations drifting.

    `psa.py` necessarily re-expresses M7's arithmetic in array form to
    vectorise it. With every distribution collapsed to a point, the array
    path must reproduce `compute_budget_impact`'s scalar answer exactly — if
    it ever stops doing so, the two have diverged and this fails.
    """
    country = _differentiated_country(zero_variance=True)
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    deterministic = compute_budget_impact(inputs).totals.cumulative.amount
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)

    assert result.mean == pytest.approx(deterministic, rel=1e-9)
    assert all(s == pytest.approx(deterministic, rel=1e-9) for s in result.samples)


def test_same_seed_produces_identical_samples() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    first = run_psa(inputs, iterations=500, seed=12345)
    second = run_psa(inputs, iterations=500, seed=12345)
    assert first.samples == second.samples


def test_different_seeds_produce_different_samples() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    first = run_psa(inputs, iterations=500, seed=1)
    second = run_psa(inputs, iterations=500, seed=2)
    assert first.samples != second.samples


def test_too_few_iterations_raises() -> None:
    inputs = make_engine_input(horizon_years=1)
    with pytest.raises(ValueError, match="iterations"):
        run_psa(inputs, iterations=50, seed=PSA_DEFAULT_SEED)


def test_too_many_iterations_raises() -> None:
    inputs = make_engine_input(horizon_years=1)
    with pytest.raises(ValueError, match="iterations"):
        run_psa(inputs, iterations=50_001, seed=PSA_DEFAULT_SEED)


def test_psa_mean_within_two_percent_of_deterministic_base() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    deterministic = compute_budget_impact(inputs).totals.cumulative.amount
    result = run_psa(inputs, iterations=5_000, seed=PSA_DEFAULT_SEED)
    assert result.mean == pytest.approx(deterministic, rel=0.02)


def test_percentiles_are_ordered() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=1_000, seed=PSA_DEFAULT_SEED)
    assert result.p2_5 <= result.median <= result.p97_5


def test_exceedance_probabilities_are_in_unit_interval() -> None:
    inputs = make_engine_input(
        countries=(_differentiated_country(),), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=1_000, seed=PSA_DEFAULT_SEED)
    assert set(result.exceedance) == {"moderate", "high", "critical"}
    assert all(0.0 <= p <= 1.0 for p in result.exceedance.values())


def test_degenerate_mean_holds_point_value_and_warns() -> None:
    country = _differentiated_country()
    # A criterion factor pinned at exactly 1.0 is outside Beta's open (0, 1)
    # support -> held at the point value with a diagnostic, not raised.
    pinned = tuple(
        c.model_copy(update={"factor": make_valued(1.0)}) for c in country.criteria
    )
    inputs = make_engine_input(
        countries=(country.model_copy(update={"criteria": pinned}),),
        horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)
    assert any(w.code == "DEGENERATE_DISTRIBUTION" for w in result.warnings)


def test_distribution_shrunk_warning_for_over_wide_tier_sd() -> None:
    country = _differentiated_country()
    # Tier D (50% RSE) on a mean near 1 gives an SD far above the Beta
    # variance ceiling -> shrink and warn rather than raise.
    wide = country.prevalence.model_copy(update={
        "value": 0.95, "low": None, "high": None,
        "provenance": make_provenance(tier=ConfidenceTier.D),
    })
    inputs = make_engine_input(
        countries=(country.model_copy(update={"prevalence": wide}),),
        horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)
    assert any(w.code == "DISTRIBUTION_SHRUNK" for w in result.warnings)


def test_unresolved_adult_share_raises() -> None:
    from biet_engine.exceptions import UnresolvedParameterError

    country = _differentiated_country().model_copy(update={"adult_share": None})
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    with pytest.raises(UnresolvedParameterError, match="adult_share"):
        run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)


def test_unresolved_health_exp_pc_raises() -> None:
    from biet_engine.exceptions import UnresolvedParameterError

    country = _differentiated_country().model_copy(update={"health_exp_pc": None})
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    with pytest.raises(UnresolvedParameterError, match="health_exp_pc"):
        run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)


def test_zero_width_published_interval_holds_the_point_value() -> None:
    country = _differentiated_country()
    pinned = country.prevalence.model_copy(update={
        "low": country.prevalence.value, "high": country.prevalence.value,
    })
    inputs = make_engine_input(
        countries=(country.model_copy(update={"prevalence": pinned}),),
        horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    # Runs cleanly and produces a real distribution from the *other*
    # (still-varying) parameters, rather than raising on the zero width.
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)
    assert result.iterations == 200


def test_inverted_published_interval_holds_the_point_value() -> None:
    # low > high yields a negative derived SD, which no distribution can use.
    # Holding the point value is the defensive response — a corrupt interval
    # shouldn't take down a whole PSA run.
    country = _differentiated_country()
    inverted = country.prevalence.model_copy(update={"low": 0.30, "high": 0.10})
    inputs = make_engine_input(
        countries=(country.model_copy(update={"prevalence": inverted}),),
        horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)
    assert result.iterations == 200


def test_therapy_outside_baseline_shares_is_skipped() -> None:
    # A comparator with no baseline share contributes no displaced volume,
    # so it must be skipped rather than indexed into baseline_shares.
    extra = make_therapy_input(drug_id=7, is_new=False, unit_price=50.0, currency="USD")
    country = _differentiated_country()
    country = country.model_copy(update={"therapies": (*country.therapies, extra)})
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    result = run_psa(inputs, iterations=200, seed=PSA_DEFAULT_SEED)
    assert result.iterations == 200


def test_five_thousand_iterations_ten_markets_under_five_seconds() -> None:
    codes = ("USA", "GBR", "DEU", "FRA", "ITA", "ESP", "JPN", "CHN", "BRA", "IND")
    countries = tuple(_differentiated_country(code, horizon=5) for code in codes)
    inputs = make_engine_input(
        countries=countries, horizon_years=5, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.02, 0.05, 0.08, 0.10, 0.12)),
    )

    start = time.perf_counter()
    result = run_psa(inputs, iterations=5_000, seed=PSA_DEFAULT_SEED)
    elapsed = time.perf_counter() - start

    assert result.iterations == 5_000
    assert elapsed < 5.0, f"took {elapsed:.2f} s, budget is 5 s"
