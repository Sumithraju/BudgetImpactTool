"""Unit tests for biet_engine.solver — M8 section 10 (reverse half)."""

from __future__ import annotations

import pytest

from biet_engine.affordability import compute_affordability
from biet_engine.constants import SolverMethod
from biet_engine.exceptions import UnresolvedParameterError
from biet_engine.impact import compute_budget_impact
from biet_engine.models import Money, Substitution
from biet_engine.solver import solve_price

from ..conftest import (
    make_country_input,
    make_engine_input,
    make_therapy_input,
    make_uptake_input,
    make_valued,
)


def _reconcile(country, inputs, entry) -> float:
    """Feeds a solved price back through M7+M8, returning the reproduced
    cumulative ratio — the module doc's "strongest single check"."""
    priced_new = country.new_therapy.model_copy(
        update={"unit_price": Money(amount=entry.max_unit_price_usd, currency=country.currency)}
    )
    priced_country = country.model_copy(update={"new_therapy": priced_new})
    priced_inputs = inputs.model_copy(update={"countries": (priced_country,)})
    result = compute_budget_impact(priced_inputs)
    return compute_affordability(result, priced_inputs)[0].cumulative_ratio


def test_analytic_price_reconciles_through_forward_pass() -> None:
    country = make_country_input(country_code="USA", currency="USD", horizon=2)
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    corridor = solve_price(inputs, target_ratio=0.005)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.ANALYTIC
    assert entry.feasible
    assert entry.max_unit_price_usd is not None

    reconciled = _reconcile(country, inputs, entry)
    assert reconciled == pytest.approx(0.005, rel=1e-6)


def test_bisection_triggered_by_substitution_floor_and_reconciles() -> None:
    # A comparator with a tiny baseline share relative to what the new
    # therapy draws from it -> the displacement floor binds -> M4 emits
    # SUBSTITUTION_FLOOR -> the analytic reduced-form basis no longer holds.
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    filler = make_therapy_input(drug_id=3, is_new=False, unit_price=50.0, currency="USD")
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=2,
        therapies=(comparator, filler), new_therapy=new_therapy,
        baseline_shares={1: (0.02, 0.02), 3: (0.98, 0.98)},
        substitution=Substitution(shares={1: make_valued(1.0), 3: make_valued(0.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=2, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05, 0.10)),
    )
    corridor = solve_price(inputs, target_ratio=0.005)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.BISECTION
    assert entry.iterations is not None and entry.iterations > 0
    assert entry.feasible
    assert entry.max_unit_price_usd is not None

    reconciled = _reconcile(country, inputs, entry)
    assert reconciled == pytest.approx(0.005, rel=1e-5)


def test_ppp_floor_binding_still_uses_analytic_path() -> None:
    # gdp_pc_ppp far below the reference market -> the PPP floor binds
    # (section 5.3's "linearity" note: max(a*p, b*p) = p*max(a,b), so the
    # floor is still a constant multiplier on p, not a piecewise function).
    # USA (the reference market, gdp_pc_ppp defaults to a DEU-ish figure via
    # the factory) must also be present for solve_price to derive ppp(IND).
    reference = make_country_input(country_code="USA", currency="USD", horizon=1)
    india = make_country_input(country_code="IND", currency="USD", horizon=1, gdp_pc_ppp=2000.0)
    inputs = make_engine_input(
        countries=(reference, india), horizon_years=1, reporting_currency="USD",
        fx_rates={"USD": 1.0},
        uptake=make_uptake_input(vector=(0.05,)),
    )
    corridor = solve_price(inputs, target_ratio=0.005)
    india_entry = next(e for e in corridor.entries if e.country_code == "IND")
    assert india_entry.method == SolverMethod.ANALYTIC


def test_sum_alpha_zero_is_unbounded() -> None:
    # Zero uptake in every year -> no patients ever reach the new therapy ->
    # alpha(c,y) = D(c,y) x ... = 0 for every year -> sum(alpha) = 0.
    country = make_country_input(country_code="USA", currency="USD", horizon=1)
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.0,)),
    )
    corridor = solve_price(inputs, target_ratio=0.005)
    entry = corridor.entries[0]
    assert entry.unbounded
    assert entry.max_unit_price_usd is None


def test_p_star_below_zero_is_infeasible_with_shortfall() -> None:
    # An extremely tight target ratio, with the new therapy's non-price costs
    # already dominating -> even a zero acquisition price can't meet target.
    new_therapy = make_therapy_input(
        drug_id=2, is_new=True, unit_price=1.0, currency="USD", admin_cost=1_000_000.0,
    )
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1, new_therapy=new_therapy,
        health_exp_pc=1.0, population_total=1000,
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.5,)),
    )
    corridor = solve_price(inputs, target_ratio=1e-9)
    entry = corridor.entries[0]
    assert not entry.feasible
    assert not entry.unbounded
    assert entry.max_unit_price_usd is None
    assert entry.shortfall_usd is not None and entry.shortfall_usd > 0


def test_analytic_missing_health_exp_pc_raises() -> None:
    country = make_country_input(country_code="USA", currency="USD", horizon=1, health_exp_pc=None)
    inputs = make_engine_input(countries=(country,), horizon_years=1, reporting_currency="USD")
    with pytest.raises(UnresolvedParameterError):
        solve_price(inputs, target_ratio=0.005)


def test_target_ratio_zero_raises() -> None:
    country = make_country_input(country_code="USA", currency="USD", horizon=1)
    inputs = make_engine_input(countries=(country,), horizon_years=1, reporting_currency="USD")
    with pytest.raises(ValueError, match="target_ratio"):
        solve_price(inputs, target_ratio=0.0)


def test_target_ratio_above_one_warns() -> None:
    country = make_country_input(country_code="USA", currency="USD", horizon=1)
    inputs = make_engine_input(countries=(country,), horizon_years=1, reporting_currency="USD")
    corridor = solve_price(inputs, target_ratio=1.5)
    assert any(w.code == "TARGET_RATIO_ABOVE_ONE" for w in corridor.warnings)


def test_corridor_picks_minimum_feasible_market_as_binding() -> None:
    # The module doc's own reasoning (section 5.7): health expenditure per
    # capita ranges from ~$13,473 (USA) to ~$85 (IND), and *that* — not the
    # PPP price-derivation ratio — is what drives India's tiny affordability
    # ceiling (H(c) is directly proportional to health_exp_pc; a much
    # smaller H(c) makes tau*H(c) - beta(c) smaller, hence a smaller p*).
    usa = make_country_input(country_code="USA", currency="USD", horizon=1,
                              gdp_pc_ppp=75_407.0, health_exp_pc=13_473.0,
                              population_total=331_000_000)
    india = make_country_input(country_code="IND", currency="USD", horizon=1,
                                gdp_pc_ppp=2_000.0, health_exp_pc=85.0,
                                population_total=1_400_000_000)
    inputs = make_engine_input(
        countries=(usa, india), horizon_years=1, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.05,)),
    )
    corridor = solve_price(inputs, target_ratio=0.005)

    assert corridor.binding_market == "IND"
    ind_entry = next(e for e in corridor.entries if e.country_code == "IND")
    assert corridor.single_global_price_ceiling_usd == ind_entry.max_unit_price_usd


def test_all_markets_infeasible_yields_no_binding_market() -> None:
    new_therapy = make_therapy_input(
        drug_id=2, is_new=True, unit_price=1.0, currency="USD", admin_cost=1_000_000.0,
    )
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1, new_therapy=new_therapy,
        health_exp_pc=1.0, population_total=1000,
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.5,)),
    )
    corridor = solve_price(inputs, target_ratio=1e-9)
    assert corridor.binding_market is None
    assert corridor.single_global_price_ceiling_usd is None


def test_missing_reference_market_raises() -> None:
    country = make_country_input(country_code="DEU", currency="EUR", horizon=1)
    inputs = make_engine_input(countries=(country,), horizon_years=1, reporting_currency="EUR")
    with pytest.raises(UnresolvedParameterError):
        solve_price(inputs, target_ratio=0.005)


def test_bisection_infeasible_at_minimum_price() -> None:
    # SUBSTITUTION_FLOOR forced (tiny baseline share for the drawn-down
    # comparator), and the new therapy's non-price costs alone already
    # exceed an extremely tight target -- infeasible even near price 0.
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    filler = make_therapy_input(drug_id=3, is_new=False, unit_price=50.0, currency="USD")
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=1.0, currency="USD",
                                      admin_cost=1_000_000.0)
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator, filler), new_therapy=new_therapy,
        baseline_shares={1: (0.0001,), 3: (0.9999,)},
        substitution=Substitution(shares={1: make_valued(1.0), 3: make_valued(0.0)}),
        health_exp_pc=1.0, population_total=1000,
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.5,)),
    )
    corridor = solve_price(inputs, target_ratio=1e-9)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.BISECTION
    assert not entry.feasible
    assert not entry.unbounded
    assert entry.max_unit_price_usd is None


def test_bisection_unbounded_even_after_widened_bracket() -> None:
    # SUBSTITUTION_FLOOR forced, uptake tiny enough that BI barely moves with
    # price, and a target so high it's never reached even at 100x p_ref.
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    filler = make_therapy_input(drug_id=3, is_new=False, unit_price=50.0, currency="USD")
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=1.0, currency="USD",
                                      admins_per_year=1.0)
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator, filler), new_therapy=new_therapy,
        baseline_shares={1: (0.000001,), 3: (0.999999,)},
        substitution=Substitution(shares={1: make_valued(1.0), 3: make_valued(0.0)}),
        health_exp_pc=100_000_000.0, population_total=1_000_000_000,
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.00001,)),
    )
    corridor = solve_price(inputs, target_ratio=0.999)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.BISECTION
    assert entry.unbounded
    assert entry.feasible
    assert entry.max_unit_price_usd is None


def test_bisection_succeeds_after_bracket_widening() -> None:
    # A target ratio that the initial [eps, 10xp_ref] bracket can't reach but
    # the widened [eps, 100xp_ref] bracket can -- the "widen, then find a
    # root after all" path, distinct from both the no-widen-needed case and
    # the widen-and-still-unbounded case covered elsewhere.
    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    filler = make_therapy_input(drug_id=3, is_new=False, unit_price=50.0, currency="USD")
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator, filler), new_therapy=new_therapy,
        baseline_shares={1: (0.02,), 3: (0.98,)},
        substitution=Substitution(shares={1: make_valued(1.0), 3: make_valued(0.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05,)),
    )
    corridor = solve_price(inputs, target_ratio=0.04)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.BISECTION
    assert entry.feasible
    assert not entry.unbounded
    assert entry.max_unit_price_usd is not None
    # p_ref=100 (new_therapy's stated unit_price) -> the un-widened bracket
    # tops out at 1,000; a solved price above that proves widening happened.
    assert entry.max_unit_price_usd > 1_000


def test_sum_alpha_negative_raises_solver_invariant_error() -> None:
    # Impossible through validated construction (units_per_admin has no
    # explicit non-negativity check, unlike admins_per_year/wastage/discount)
    # — exercises the "impossible by construction" guard directly, per its
    # own docstring, by constructing the one field this system doesn't
    # actually validate.
    from biet_engine.exceptions import SolverInvariantError

    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=100.0, currency="USD")
    negative_regimen = new_therapy.regimen.model_copy(
        update={"units_per_admin": make_valued(-1.0)}
    )
    new_therapy = new_therapy.model_copy(update={"regimen": negative_regimen})
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1, new_therapy=new_therapy,
    )
    inputs = make_engine_input(countries=(country,), horizon_years=1, reporting_currency="USD")
    with pytest.raises(SolverInvariantError):
        solve_price(inputs, target_ratio=0.005)


def test_bisection_non_convergence_reports_none_never_a_partial_value() -> None:
    from biet_engine.solver import _bisect

    # A genuinely monotonic, convergent objective -- but capped at a single
    # iteration, nowhere near enough to reach the default tolerance for this
    # bracket width. Exercises the "exhausted max_iterations" branch
    # directly, since standard bisection with the real 100-iteration/1e-6
    # tolerance defaults always converges in ~20-30 iterations for any
    # realistic bracket and can't reach this path through solve_price itself.
    price, iterations = _bisect(lambda p: p - 500.0, lo=0.0, hi=1_000_000.0, max_iterations=1)
    assert price is None
    assert iterations == 1


def test_solve_bisection_non_convergence_reports_infeasible(monkeypatch) -> None:
    # Same idea, but through the real _solve_bisection integration (section
    # 5.5: "never return a partially converged value"), by capping the
    # module-level iteration budget it reads at call time rather than
    # constructing a pathological bracket -- ordinary brackets always
    # converge in ~20-30 iterations, well under the real 100-iteration cap.
    import biet_engine.solver as solver_module

    monkeypatch.setattr(solver_module, "SOLVER_MAX_ITERATIONS", 1)

    comparator = make_therapy_input(drug_id=1, is_new=False, unit_price=100.0, currency="USD")
    filler = make_therapy_input(drug_id=3, is_new=False, unit_price=50.0, currency="USD")
    new_therapy = make_therapy_input(drug_id=2, is_new=True, unit_price=100.0, currency="USD")
    country = make_country_input(
        country_code="USA", currency="USD", horizon=1,
        therapies=(comparator, filler), new_therapy=new_therapy,
        baseline_shares={1: (0.02,), 3: (0.98,)},
        substitution=Substitution(shares={1: make_valued(1.0), 3: make_valued(0.0)}),
    )
    inputs = make_engine_input(
        countries=(country,), horizon_years=1, reporting_currency="USD",
        uptake=make_uptake_input(vector=(0.05,)),
    )
    corridor = solver_module.solve_price(inputs, target_ratio=0.005)
    entry = corridor.entries[0]

    assert entry.method == SolverMethod.BISECTION
    assert not entry.feasible
    assert not entry.unbounded
    assert entry.max_unit_price_usd is None
    assert entry.iterations == 1
