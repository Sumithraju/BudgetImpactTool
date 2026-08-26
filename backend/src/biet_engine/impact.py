"""Budget Impact Calculator — ARCHITECTURE.md section 5.6, module M7.

Executes the incremental world-with versus world-without comparison and
aggregates the result across therapies, markets and years. This is the
definitional core of the system: everything upstream (M2-M6) resolves inputs
this module turns into a number.

Performance note (acceptance criterion "array-based... ready for M9's 5,000
iterations"): the inner loop here is plain Python over `markets x years`
(<=50 iterations at the 10x5 target scale), not NumPy-vectorised. It clears
the <200ms budget by a wide margin at that scale (see the benchmark test),
so vectorising now would be optimising code with no measured cost. M9's PSA
workload (5,000 repeated calls) doesn't exist yet; revisit this loop when
M9 is built and can say whether the call overhead actually matters against
real numbers, rather than vectorising against a guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from . import __version__
from .cost import compute_therapy_cost
from .eligibility import combine_criteria
from .funnel import compute_funnel
from .fx import convert
from .models import (
    CountryInput,
    CountryResult,
    EngineInput,
    EngineResult,
    FunnelResult,
    Money,
    Totals,
    Warning_,
    YearResult,
)
from .persistence import persistence_fraction
from .uptake import build_market_mix, project_uptake


class _ComparatorYearTerm(NamedTuple):
    m_without: float
    m_with: float
    sigma: float
    persistence: float
    annual_cost: float                       # local currency amount


def _year_result(
    *,
    year: int,
    launch_year: int,
    currency: str,
    addressable: float,
    uptake: float,
    new_persistence: float,
    new_annual_cost: float,
    comparators: Sequence[_ComparatorYearTerm],
) -> YearResult:
    """The full two-world subtraction (section 5.1), for one market and year.

        Cost_without = Addressable x sum_t [ m_without(t) x f_t x AC(t) ]
        Cost_with    = Addressable x [ u x f_n x AC(n)
                                        + sum_t m_with(t) x f_t x AC(t) ]
        BI           = Cost_with - Cost_without

    Implements the full form, not the reduced form — the reduced form
    (section 5.2) assumes `m_with = m_without - u*sigma` exactly, which stops
    holding the moment M4's displacement floor binds and redistributes. The
    reduced form is used only as a property test, per the module doc.

    Nothing here is rounded. Rounding happens once, at serialisation
    (section 5.7) — not implemented in this module.
    """
    cost_without_per_addressable = sum(t.m_without * t.persistence * t.annual_cost
                                        for t in comparators)
    cost_with_per_addressable = uptake * new_persistence * new_annual_cost + sum(
        t.m_with * t.persistence * t.annual_cost for t in comparators
    )

    cost_without = Money(amount=addressable * cost_without_per_addressable, currency=currency)
    cost_with = Money(amount=addressable * cost_with_per_addressable, currency=currency)
    budget_impact = cost_with - cost_without

    patients_on_new = addressable * uptake
    impact_per_patient = (
        Money(amount=budget_impact.amount / patients_on_new, currency=currency)
        if patients_on_new > 0 else None
    )

    net_cost_per_switch = Money(
        amount=new_persistence * new_annual_cost
        - sum(t.sigma * t.persistence * t.annual_cost for t in comparators),
        currency=currency,
    )

    return YearResult(
        year=year, calendar_year=launch_year + year - 1, uptake=uptake,
        addressable=addressable, patients_on_new=patients_on_new,
        cost_without=cost_without, cost_with=cost_with, budget_impact=budget_impact,
        impact_per_patient=impact_per_patient, net_cost_per_switch=net_cost_per_switch,
    )


def _compute_country_result(
    country: CountryInput, uptake_vector: Sequence[float], launch_year: int,
) -> tuple[CountryResult, tuple[Warning_, ...]]:
    new_drug_id = country.new_therapy.drug_id
    if any(t.drug_id == new_drug_id for t in country.therapies):
        raise ValueError(
            f"new therapy (drug_id={new_drug_id}) must not appear in the "
            "comparator set"
        )
    missing = set(country.baseline_shares) - {t.drug_id for t in country.therapies}
    if missing:
        raise ValueError(
            f"baseline_shares names drug_id(s) with no matching therapy: {sorted(missing)}"
        )

    criteria_result = combine_criteria(country.criteria)
    market_mixes = build_market_mix(
        country.baseline_shares, uptake_vector, country.substitution, country.country_code,
    )

    new_cost = compute_therapy_cost(country.new_therapy, country.country_code)
    new_persistence = persistence_fraction(country.new_therapy.persistence_12m.value)

    costs = {t.drug_id: compute_therapy_cost(t, country.country_code) for t in country.therapies}
    persistences = {
        t.drug_id: persistence_fraction(t.persistence_12m.value) for t in country.therapies
    }
    sigma = {drug_id: s.value for drug_id, s in country.substitution.shares.items()}

    warnings: list[Warning_] = list(criteria_result.warnings)
    years: list[YearResult] = []
    funnel_year_1: FunnelResult | None = None

    for index, u in enumerate(uptake_vector):
        year = index + 1
        funnel_result = compute_funnel(country, criteria_result.combined_factor, year)
        if year == 1:
            funnel_year_1 = funnel_result

        mix = market_mixes[index]
        warnings.extend(mix.warnings)

        comparators = [
            _ComparatorYearTerm(
                m_without=mix.shares_without[drug_id],
                m_with=mix.shares_with[drug_id],
                sigma=sigma.get(drug_id, 0.0),
                persistence=persistences[drug_id],
                annual_cost=costs[drug_id].total.amount,
            )
            for drug_id in country.baseline_shares
        ]

        years.append(_year_result(
            year=year, launch_year=launch_year, currency=country.currency,
            addressable=funnel_result.addressable, uptake=u,
            new_persistence=new_persistence, new_annual_cost=new_cost.total.amount,
            comparators=comparators,
        ))

    assert funnel_year_1 is not None                # horizon >= 1 always, per EngineInput

    cumulative = Money(amount=0.0, currency=country.currency)
    for yr in years:
        cumulative = cumulative + yr.budget_impact

    return (
        CountryResult(
            country_code=country.country_code, currency=country.currency,
            funnel=funnel_year_1, years=tuple(years), cumulative_budget_impact=cumulative,
        ),
        tuple(warnings),
    )


def compute_budget_impact(inputs: EngineInput) -> EngineResult:
    """The incremental budget impact of the new therapy, per market and
    year, aggregated to the reporting currency.

    Args:
        inputs: the fully-resolved run — every market, every scenario
            parameter, the FX snapshot to convert with.

    Returns:
        Per-market results in local currency, plus cross-market totals in
        `inputs.reporting_currency`.

    Raises:
        ValueError: the new therapy appears in its own comparator set, or a
            market's baseline shares reference a therapy with no cost data.
        MissingFxRateError: a market's currency, or the reporting currency,
            has no rate in `inputs.fx_rates`.
        UnresolvedParameterError, FunnelInvariantError, UnknownTherapyError,
        DisplacementError, CorrelatedCriteriaError: propagated from M2-M4.
    """
    uptake_vector = project_uptake(inputs.uptake, inputs.horizon_years)

    country_results: list[CountryResult] = []
    all_warnings: list[Warning_] = []
    for country in inputs.countries:
        result, warnings = _compute_country_result(country, uptake_vector, inputs.launch_year)
        country_results.append(result)
        all_warnings.extend(warnings)

    by_year_totals: list[Money] = []
    without_totals: list[Money] = []
    with_totals: list[Money] = []
    for index in range(inputs.horizon_years):
        zero = Money(amount=0.0, currency=inputs.reporting_currency)
        year_total, year_without, year_with = zero, zero, zero
        for country_result in country_results:
            year = country_result.years[index]
            # All three convert through the same snapshot, so the identity
            # with - without = impact survives aggregation exactly.
            year_total = year_total + convert(
                year.budget_impact, inputs.reporting_currency, inputs.fx_rates,
            )
            year_without = year_without + convert(
                year.cost_without, inputs.reporting_currency, inputs.fx_rates,
            )
            year_with = year_with + convert(
                year.cost_with, inputs.reporting_currency, inputs.fx_rates,
            )
        by_year_totals.append(year_total)
        without_totals.append(year_without)
        with_totals.append(year_with)

    cumulative = Money(amount=0.0, currency=inputs.reporting_currency)
    for total in by_year_totals:
        cumulative = cumulative + total

    peak_year = max(range(1, inputs.horizon_years + 1),
                     key=lambda y: by_year_totals[y - 1].amount)

    return EngineResult(
        engine_version=__version__,
        reporting_currency=inputs.reporting_currency,
        fx_snapshot_date=inputs.fx_snapshot_date,
        countries=tuple(country_results),
        totals=Totals(
            by_year=tuple(by_year_totals),
            cumulative=cumulative,
            peak_year=peak_year,
            without_by_year=tuple(without_totals),
            with_by_year=tuple(with_totals),
        ),
        warnings=tuple(all_warnings),
    )
