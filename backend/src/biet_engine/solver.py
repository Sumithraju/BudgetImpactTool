"""Affordability & Price Solver, reverse mode — ARCHITECTURE.md section 5.8,
module M8.

Given an affordability ceiling `target_ratio`, solves for the maximum unit
price of the new therapy, per market — the reverse of `compute_budget_impact`.
The solve variable is the new therapy's unit price **in the reference market,
in USD**; every other market's price is derived from it through M5's PPP
factor (section 5.3), since a pre-launch asset has no observed price
anywhere. The whole solve is performed in USD.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .affordability import compute_affordability
from .constants import (
    PPP_DEFAULT_ELASTICITY,
    PPP_PRICE_FLOOR,
    REFERENCE_MARKET,
    SOLVER_BRACKET_MULTIPLIER,
    SOLVER_BRACKET_WIDEN_MULTIPLIER,
    SOLVER_MAX_ITERATIONS,
    SOLVER_RELATIVE_TOLERANCE,
    SolverMethod,
)
from .cost import compute_therapy_cost, derive_ppp_price
from .eligibility import combine_criteria
from .exceptions import SolverInvariantError, UnresolvedParameterError
from .funnel import compute_funnel, project_population
from .fx import convert
from .impact import compute_budget_impact
from .models import CorridorEntry, CountryInput, EngineInput, Money, PriceCorridor, Warning_
from .persistence import persistence_fraction
from .uptake import build_market_mix, project_uptake

#: Effectively zero for a positive-price-only TherapyInput (unit_price must
#: be > 0), used as the bisection bracket's lower bound in place of literal 0.
_EPSILON_PRICE_USD = 1e-9


def solve_price(inputs: EngineInput, target_ratio: float) -> PriceCorridor:
    """The maximum new-therapy unit price (USD, reference market) each
    market can afford at `target_ratio`, and the cross-market corridor.

    Args:
        inputs: the run to solve against. Each market's `new_therapy.
            unit_price` is not read as an observed price — reverse mode
            assumes none exists — except for the reference market (`USA`),
            where it doubles as `p_ref`, the bisection bracket's anchor
            ("the scenario's stated reference price", section 5.5).
        target_ratio: the affordability ceiling, tau. Must be positive.

    Returns:
        One `CorridorEntry` per market plus the binding market (the one
        setting the global price ceiling) and that ceiling itself.

    Raises:
        ValueError: `target_ratio <= 0`.
        UnresolvedParameterError: the reference market (`USA`) is not
            present in `inputs.countries`, or a market's `health_exp_pc` is
            unresolved. The module doc calls a *missing* reference market
            "permitted — ppp(ref) is still computable", but doesn't say from
            where; requiring it in the market set is the documented
            simplification this implementation makes instead of inventing an
            undefined data source.
        SolverInvariantError: `sum(alpha) < 0` for some market — impossible
            by construction, since every factor in it is non-negative.
    """
    if target_ratio <= 0:
        raise ValueError(f"target_ratio must be positive, got {target_ratio!r}")

    warnings: list[Warning_] = []
    if target_ratio > 1:
        warnings.append(Warning_(
            code="TARGET_RATIO_ABOVE_ONE",
            message=f"target_ratio={target_ratio!r} exceeds total health expenditure; "
                    "a ceiling above 1.0 is not a meaningful affordability constraint",
        ))

    reference = next(
        (c for c in inputs.countries if c.country_code == REFERENCE_MARKET), None,
    )
    if reference is None:
        raise UnresolvedParameterError(
            f"reference market {REFERENCE_MARKET!r} is not in inputs.countries",
        )
    gdp_pc_ppp_reference = reference.gdp_pc_ppp.value
    p_ref_usd = convert(reference.new_therapy.unit_price, "USD", inputs.fx_rates).amount

    uptake_vector = project_uptake(inputs.uptake, inputs.horizon_years)

    entries = []
    for country in inputs.countries:
        entry, entry_warnings = _solve_for_country(
            country, inputs, uptake_vector, target_ratio, gdp_pc_ppp_reference, p_ref_usd,
        )
        entries.append(entry)
        warnings.extend(entry_warnings)

    feasible_entries = [e for e in entries if e.feasible and not e.unbounded]
    if feasible_entries:
        binding = min(feasible_entries, key=lambda e: e.max_unit_price_usd or float("inf"))
        binding_market: str | None = binding.country_code
        ceiling: float | None = binding.max_unit_price_usd
    else:
        binding_market = None
        ceiling = None

    return PriceCorridor(
        target_ratio=target_ratio, entries=tuple(entries),
        binding_market=binding_market, single_global_price_ceiling_usd=ceiling,
        warnings=tuple(warnings),
    )


def _solve_for_country(
    country: CountryInput,
    inputs: EngineInput,
    uptake_vector: Sequence[float],
    target_ratio: float,
    gdp_pc_ppp_reference: float,
    p_ref_usd: float,
) -> tuple[CorridorEntry, list[Warning_]]:
    regimen = country.new_therapy.regimen
    units = regimen.units_per_admin.value * regimen.admins_per_year.value
    wastage = regimen.wastage_pct.value
    discount = country.new_therapy.discount_pct.value

    def _acquisition_from_unit_price(unit_price_usd: float) -> float:
        return unit_price_usd * units * (1 + wastage) * (1 - discount)

    market_mixes = build_market_mix(
        country.baseline_shares, uptake_vector, country.substitution, country.country_code,
    )
    substitution_floor = any(
        w.code == "SUBSTITUTION_FLOOR" for mix in market_mixes for w in mix.warnings
    )

    shortfall_usd: float | None = None
    if substitution_floor:
        price_usd, feasible, unbounded, method, iterations = _solve_bisection(
            country, inputs, target_ratio, p_ref_usd,
        )
    else:
        price_usd, feasible, unbounded, shortfall_usd = _solve_analytic(
            country, inputs, uptake_vector, target_ratio, gdp_pc_ppp_reference,
        )
        method, iterations = SolverMethod.ANALYTIC, None

    max_annual = _acquisition_from_unit_price(price_usd) if price_usd is not None else None

    entry_warnings: list[Warning_] = []
    if unbounded:
        entry_warnings.append(Warning_(
            code="UNBOUNDED_PRICE",
            message="no patients reach the new therapy at any year, or the price "
                    "corridor extends beyond the widened bracket; any price satisfies "
                    "the target ratio",
            country_code=country.country_code,
        ))

    return (
        CorridorEntry(
            country_code=country.country_code, max_unit_price_usd=price_usd,
            max_annual_acquisition_usd=max_annual, feasible=feasible, unbounded=unbounded,
            method=method, iterations=iterations, shortfall_usd=shortfall_usd,
        ),
        entry_warnings,
    )


def _solve_analytic(
    country: CountryInput,
    inputs: EngineInput,
    uptake_vector: Sequence[float],
    target_ratio: float,
    gdp_pc_ppp_reference: float,
) -> tuple[float | None, bool, bool, float | None]:
    """The linear decomposition (section 5.3) solved in closed form (5.4).

        D(c,y)  = Addressable(c,y) x u(y)
        ppp(c)  = max( [gdp_pc_ppp(c)/gdp_pc_ppp(ref)]^eps, floor )
        alpha(c,y) = D(c,y) x f_n x U x (1+w_n) x (1-d_n) x ppp(c)
        beta(c,y)  = D(c,y) x [ f_n x (admin_n+monitoring_n+ae_n-offset_n)
                                - sum_t sigma_t x f_t x AC(t,c) ]
        p*(c) = (tau x sum_y H(c,y) - sum_y beta(c,y)) / sum_y alpha(c,y)

    Returns:
        `(p_star_usd, feasible, unbounded, shortfall_usd)`. `shortfall_usd`
        (section 5.6's `sum(beta) - tau*sum(H)`) is set only when infeasible.
    """
    if country.health_exp_pc is None:
        raise UnresolvedParameterError(
            f"health_exp_pc is unresolved for {country.country_code}",
            country_code=country.country_code,
        )
    health_exp_pc = country.health_exp_pc.value

    criteria_result = combine_criteria(country.criteria)

    new_therapy = country.new_therapy
    f_n = persistence_fraction(new_therapy.persistence_12m.value)
    regimen = new_therapy.regimen
    U = regimen.units_per_admin.value * regimen.admins_per_year.value
    w_n = regimen.wastage_pct.value
    d_n = new_therapy.discount_pct.value
    ppp = derive_ppp_price(1.0, country.gdp_pc_ppp.value, gdp_pc_ppp_reference,
                            PPP_DEFAULT_ELASTICITY, PPP_PRICE_FLOOR)

    non_price_new_usd = sum(
        convert(cost, "USD", inputs.fx_rates).amount
        for cost in (new_therapy.admin_cost, new_therapy.monitoring_cost, new_therapy.ae_cost)
    ) - convert(new_therapy.offset, "USD", inputs.fx_rates).amount

    comparator_terms = []
    sigma = {drug_id: s.value for drug_id, s in country.substitution.shares.items()}
    for therapy in country.therapies:
        f_t = persistence_fraction(therapy.persistence_12m.value)
        ac_t_usd = convert(
            compute_therapy_cost(therapy, country.country_code).total, "USD", inputs.fx_rates,
        ).amount
        comparator_terms.append((sigma.get(therapy.drug_id, 0.0), f_t, ac_t_usd))

    alpha_sum = 0.0
    beta_sum = 0.0
    health_budget_sum = 0.0
    for index, u in enumerate(uptake_vector):
        year = index + 1
        funnel_result = compute_funnel(country, criteria_result.combined_factor, year)
        d_cy = funnel_result.addressable * u

        alpha_sum += d_cy * f_n * U * (1 + w_n) * (1 - d_n) * ppp
        beta_sum += d_cy * (
            f_n * non_price_new_usd
            - sum(sigma_t * f_t * ac_t for sigma_t, f_t, ac_t in comparator_terms)
        )
        pop = project_population(country.population_total, country.population_growth, year)
        health_budget_sum += health_exp_pc * pop

    if alpha_sum < 0:
        raise SolverInvariantError(
            f"sum(alpha) is negative for {country.country_code}: {alpha_sum!r}",
            country_code=country.country_code,
        )
    if alpha_sum == 0:
        return None, True, True, None

    p_star = (target_ratio * health_budget_sum - beta_sum) / alpha_sum
    if p_star < 0:
        shortfall = beta_sum - target_ratio * health_budget_sum
        return None, False, False, shortfall
    return p_star, True, False, None


def _bisect(
    objective: Callable[[float], float],
    lo: float,
    hi: float,
    *,
    max_iterations: int = SOLVER_MAX_ITERATIONS,
    relative_tolerance: float = SOLVER_RELATIVE_TOLERANCE,
) -> tuple[float | None, int]:
    """Standard bracketed bisection on a monotonically-increasing `objective`.

    Assumes the bracket is already validated (`objective(lo) <= 0 <=
    objective(hi)`) — `_solve_bisection` does that check itself, since it
    needs the bracket-widening and infeasible/unbounded logic around it that
    doesn't belong in a generic bisection routine.

    Returns:
        `(converged_value, iterations)`. `converged_value` is `None` if
        `max_iterations` was exhausted without meeting `relative_tolerance`
        — section 5.5's "never return a partially converged value."
    """
    mid = hi
    for iterations in range(1, max_iterations + 1):
        mid = (lo + hi) / 2
        if (hi - lo) / hi < relative_tolerance:
            return mid, iterations
        if objective(mid) > 0:
            hi = mid
        else:
            lo = mid
    return None, max_iterations


def _solve_bisection(
    country: CountryInput, inputs: EngineInput, target_ratio: float, p_ref_usd: float,
) -> tuple[float | None, bool, bool, SolverMethod, int | None]:
    """Runs the full M7+M8 forward pass at trial prices (section 5.5),
    triggered when M4 reported a `SUBSTITUTION_FLOOR` for this market — the
    reduced form the analytic path rests on doesn't hold there."""

    def objective(unit_price_usd: float) -> float:
        return _cumulative_ratio_at_price(country, unit_price_usd, inputs) - target_ratio

    lo, hi = _EPSILON_PRICE_USD, p_ref_usd * SOLVER_BRACKET_MULTIPLIER

    if objective(lo) > 0:
        return None, False, False, SolverMethod.BISECTION, 0

    if objective(hi) < 0:
        hi = p_ref_usd * SOLVER_BRACKET_WIDEN_MULTIPLIER
        if objective(hi) < 0:
            return None, True, True, SolverMethod.BISECTION, 0

    # Read module-level constants at call time, not via _bisect's default
    # parameter binding, so a test can override SOLVER_MAX_ITERATIONS to
    # exercise the non-convergence path through this real integration rather
    # than only through _bisect in isolation.
    price, iterations = _bisect(
        objective, lo, hi,
        max_iterations=SOLVER_MAX_ITERATIONS, relative_tolerance=SOLVER_RELATIVE_TOLERANCE,
    )
    if price is None:
        return None, False, False, SolverMethod.BISECTION, iterations
    return price, True, False, SolverMethod.BISECTION, iterations


def _cumulative_ratio_at_price(
    country: CountryInput, unit_price_usd: float, inputs: EngineInput,
) -> float:
    local_price = convert(
        Money(amount=unit_price_usd, currency="USD"), country.currency, inputs.fx_rates,
    ).amount
    priced_country = country.model_copy(update={
        "new_therapy": country.new_therapy.model_copy(update={
            "unit_price": Money(amount=local_price, currency=country.currency),
        }),
    })
    single_market_inputs = inputs.model_copy(update={
        "countries": (priced_country,), "reporting_currency": country.currency,
    })
    result = compute_budget_impact(single_market_inputs)
    return compute_affordability(result, single_market_inputs)[0].cumulative_ratio
