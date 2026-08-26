"""Payer perspective and decision views — M17.

The same computation, framed for the budget holder actually reading it.

An insurer covering four million lives, a self-insured employer covering forty
thousand and a national health system are not looking at the same number. They
divide by different denominators, and a per-member figure quoted against the
wrong one is not slightly wrong — it is wrong by whatever ratio separates the
covered population from the nation, which for an employer is three orders of
magnitude. So the denominator is an input here, and when it has to be assumed
the result says so on the figure rather than in a footnote.

Three views live in this module:

**Per-member-per-month.** M8 already computes PMPY against national health
expenditure. PMPM against *covered lives* is the figure a US payer conversation
actually opens with, and it is not PMPY over twelve unless the denominators
match — which, for anyone but a health system, they do not.

**Break-even price.** M8's solver targets an affordability *ratio*. Break-even
targets zero: the price at which the new therapy costs exactly what the care it
displaces costs today. It is the more useful number in a pricing discussion
because it needs no threshold to be agreed first.

**Low, medium and high uptake.** Three runs of the same scenario, reported side
by side. Deliberately *not* an uncertainty interval — M9's PSA is that. This is
a framing device: no source supplies an adoption distribution for an unlaunched
asset, so the three cases are stated multipliers a reader can argue with.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from sqlalchemy.orm import Session

from biet_engine.fx import convert
from biet_engine.impact import compute_budget_impact
from biet_engine.models import CountryInput, EngineInput, EngineResult, Money, Warning_

from ..constants.domain import (
    SUBSET_PERSPECTIVES,
    UPTAKE_SCENARIO_MULTIPLIER,
    Perspective,
    UptakeScenario,
    WarningCode,
)
from ..schemas.calculation import (
    BreakEvenRead,
    CalculationResponse,
    CountryRead,
    PayerViewRead,
    UptakeCaseRead,
)

MONTHS_PER_YEAR = 12

PERSPECTIVE_LABELS: dict[str, str] = {
    Perspective.INSURER: "Commercial insurer",
    Perspective.EMPLOYER: "Self-insured employer",
    Perspective.GOVERNMENT: "Government payer",
    Perspective.HEALTH_SYSTEM: "National health system",
}

UPTAKE_CASE_LABELS: dict[str, str] = {
    UptakeScenario.LOW: "Conservative adoption",
    UptakeScenario.BASE: "Base case",
    UptakeScenario.HIGH: "Rapid adoption",
}

#: Bisection bounds for break-even, as multiples of the current unit price.
#: The upper bound only matters when displaced care is more expensive than the
#: new therapy at its current price — a market already saving money, where
#: break-even lies *above* today's price rather than below it.
_BREAK_EVEN_LOW_FACTOR = 0.0
_BREAK_EVEN_HIGH_FACTOR = 8.0
_BREAK_EVEN_TOLERANCE = 1e-7
_BREAK_EVEN_MAX_ITERATIONS = 80


class PayerService:
    """Perspective-framed views over an already-computed result."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- PMPM

    def payer_view(
        self,
        *,
        perspective: str,
        covered_population: int | None,
        currency: str,
        budget_impact_by_year: Sequence[float],
        cost_without_by_year: Sequence[float],
        cost_with_by_year: Sequence[float],
        patients_by_year: Sequence[float],
        fallback_population: float,
    ) -> tuple[PayerViewRead, tuple[Warning_, ...]]:
        """Per-member figures against the perspective's own denominator.

        `fallback_population` is the modelled national population, used only
        when a subset perspective did not supply covered lives. That
        substitution is always warned about: it is the single most misleading
        default this module could have, because the resulting PMPM looks
        entirely plausible and is wrong by the ratio of the two populations.
        """
        warnings: list[Warning_] = []
        assumed = False
        population = float(covered_population) if covered_population else 0.0

        if population <= 0:
            population = fallback_population
            assumed = Perspective(perspective) in SUBSET_PERSPECTIVES
            if assumed:
                warnings.append(Warning_(
                    code=WarningCode.COVERED_POPULATION_ASSUMED,
                    message=(
                        f"No covered population was given for a "
                        f"{PERSPECTIVE_LABELS[perspective].lower()} perspective, so the "
                        f"modelled national population ({fallback_population:,.0f}) "
                        "stands in. Every per-member figure below is therefore a "
                        "national average, not this payer's. Enter covered lives to "
                        "make them the payer's own."
                    ),
                ))

        pmpy = [
            impact / population if population > 0 else 0.0
            for impact in budget_impact_by_year
        ]
        pmpm = [value / MONTHS_PER_YEAR for value in pmpy]
        cumulative_impact = math.fsum(budget_impact_by_year)
        horizon = max(len(budget_impact_by_year), 1)
        cumulative_pmpm = (
            cumulative_impact / population / MONTHS_PER_YEAR / horizon
            if population > 0 else 0.0
        )

        total_patients = math.fsum(patients_by_year)
        return (
            PayerViewRead(
                perspective=perspective,
                perspective_label=PERSPECTIVE_LABELS[perspective],
                currency=currency,
                covered_population=population,
                covered_population_is_assumed=assumed,
                pmpm_by_year=pmpm,
                pmpy_by_year=pmpy,
                cumulative_pmpm=cumulative_pmpm,
                patients_treated_by_year=list(patients_by_year),
                cost_per_treated_patient=(
                    cumulative_impact / total_patients if total_patients > 0 else 0.0
                ),
                total_cost_current_care=list(cost_without_by_year),
                total_cost_with_intervention=list(cost_with_by_year),
            ),
            tuple(warnings),
        )

    @staticmethod
    def aggregate_payer_view(
        response: CalculationResponse, *, perspective: str, covered_population: int | None,
        fx_rates: dict[str, float],
    ) -> PayerViewRead | None:
        """The cross-market payer view, in the reporting currency.

        Every market's local figures are converted through the run's FX
        snapshot before they are summed — the same rule M7 follows, and for the
        same reason: adding EUR to JPY produces a number with no unit.
        """
        if not response.countries:
            return None

        reporting = response.reporting_currency
        horizon = response.horizon_years
        without = [0.0] * horizon
        with_ = [0.0] * horizon
        patients = [0.0] * horizon

        for country in response.countries:
            for index, year in enumerate(country.years[:horizon]):
                without[index] += convert(
                    Money(amount=year.cost_without, currency=country.currency),
                    reporting, fx_rates,
                ).amount
                with_[index] += convert(
                    Money(amount=year.cost_with, currency=country.currency),
                    reporting, fx_rates,
                ).amount
                patients[index] += year.patients_on_new

        # The covered population for a multi-market run is whatever the payer
        # said it was. There is no defensible way to derive one denominator
        # across markets: a payer covering lives in five countries is five
        # payers, and summing national populations would answer a question
        # nobody asked.
        population = float(covered_population) if covered_population else 0.0
        assumed = False
        if population <= 0:
            population = sum(
                country.funnel[0].value for country in response.countries
                if country.funnel
            )
            assumed = Perspective(perspective) in SUBSET_PERSPECTIVES

        impact = response.totals.by_year
        pmpy = [v / population if population > 0 else 0.0 for v in impact]
        total_patients = math.fsum(patients)

        return PayerViewRead(
            perspective=perspective,
            perspective_label=PERSPECTIVE_LABELS[perspective],
            currency=reporting,
            covered_population=population,
            covered_population_is_assumed=assumed,
            pmpm_by_year=[v / MONTHS_PER_YEAR for v in pmpy],
            pmpy_by_year=pmpy,
            cumulative_pmpm=(
                response.totals.cumulative / population / MONTHS_PER_YEAR / max(horizon, 1)
                if population > 0 else 0.0
            ),
            patients_treated_by_year=patients,
            cost_per_treated_patient=(
                response.totals.cumulative / total_patients if total_patients > 0 else 0.0
            ),
            total_cost_current_care=without,
            total_cost_with_intervention=with_,
        )

    # ----------------------------------------------------------------- break-even

    def break_even(
        self, engine_input: EngineInput,
    ) -> tuple[list[BreakEvenRead], tuple[Warning_, ...]]:
        """The unit price at which each market's cumulative impact is zero.

        Solved by bisection on the *real* forward pass rather than analytically.
        M8's analytic decomposition rests on budget impact being linear in
        price, which it is — but the bracket here spans zero, and at a low
        enough price the displacement floor and the PPP floor can both bind and
        break that linearity. Eighty bisection steps on a sub-millisecond
        forward pass costs nothing measurable and is right in every case, so
        the cheaper path is not worth the class of error it would admit.

        A market can have no break-even price: if the new therapy is already
        cheaper than the care it displaces, impact is negative at every price
        down to zero and there is nothing to solve. That is reported as
        infeasible with the reason, not as a failure.
        """
        entries: list[BreakEvenRead] = []
        warnings: list[Warning_] = []

        for country in engine_input.countries:
            price = country.new_therapy.unit_price.amount
            annual = self._annual_acquisition(country)

            impact_now = self._impact_at(engine_input, country.country_code, price)
            impact_at_zero = self._impact_at(engine_input, country.country_code, 0.0)

            if impact_at_zero > 0:
                # Free drug still costs the payer more than current care —
                # the new therapy displaces nothing cheap enough. Real when a
                # therapy adds to care rather than replacing it.
                entries.append(BreakEvenRead(
                    country_code=country.country_code,
                    currency=country.currency,
                    current_unit_price=price,
                    break_even_unit_price=None,
                    current_annual_cost=annual,
                    break_even_annual_cost=None,
                    headroom_pct=None,
                    feasible=False,
                    method="none",
                    note=(
                        "Cumulative impact stays positive even at a price of zero, so "
                        "no break-even price exists. The therapy is adding to current "
                        "care rather than displacing enough of it — check the "
                        "source-of-business assumptions before reading this as a "
                        "pricing conclusion."
                    ),
                ))
                continue

            if impact_now < 0:
                # Already saving. Break-even lies above today's price, and
                # finding it tells the payer how much headroom the asset has.
                high = price * _BREAK_EVEN_HIGH_FACTOR if price > 0 else 1.0
                if self._impact_at(engine_input, country.country_code, high) < 0:
                    entries.append(BreakEvenRead(
                        country_code=country.country_code,
                        currency=country.currency,
                        current_unit_price=price,
                        break_even_unit_price=None,
                        current_annual_cost=annual,
                        break_even_annual_cost=None,
                        headroom_pct=None,
                        feasible=False,
                        method="unbounded",
                        note=(
                            f"This market saves money at every price up to "
                            f"{_BREAK_EVEN_HIGH_FACTOR:.0f}x today's. The break-even "
                            "price is above the searched range, which usually means the "
                            "displaced comparators are priced on a different basis from "
                            "the new asset — read the mixed-basis warning first."
                        ),
                    ))
                    continue
                low, high_bound = price, high
            else:
                low, high_bound = 0.0, price

            solved = self._bisect(engine_input, country.country_code, low, high_bound)
            ratio = solved / price if price > 0 else 0.0
            entries.append(BreakEvenRead(
                country_code=country.country_code,
                currency=country.currency,
                current_unit_price=price,
                break_even_unit_price=solved,
                current_annual_cost=annual,
                break_even_annual_cost=annual * ratio,
                headroom_pct=ratio - 1.0,
                feasible=True,
                method="bisection",
                note=None,
            ))

        if not entries:
            warnings.append(Warning_(
                code="NO_BREAK_EVEN",
                message="No market in this scenario could be solved for break-even.",
            ))
        return entries, tuple(warnings)

    @staticmethod
    def _annual_acquisition(country: CountryInput) -> float:
        """Annual acquisition cost at the current price, before discount.

        The figure an analyst recognises. A unit price of 0.45 per unit means
        nothing on sight; EUR 4,979 a year is immediately either right or wrong
        to someone who knows the market.
        """
        therapy = country.new_therapy
        regimen = therapy.regimen
        return (
            therapy.unit_price.amount
            * regimen.units_per_admin.value
            * regimen.admins_per_year.value
            * (1.0 + regimen.wastage_pct.value)
        )

    @staticmethod
    def _with_price(
        engine_input: EngineInput, country_code: str, price: float,
    ) -> EngineInput:
        """The same input with one market's new-therapy price replaced.

        Rebuilt through `model_copy` rather than mutated: `EngineInput` is
        frozen by contract, and a solver that mutated its input would corrupt
        the snapshot the run is persisted from.
        """
        countries = []
        for country in engine_input.countries:
            if country.country_code != country_code:
                countries.append(country)
                continue
            therapy = country.new_therapy.model_copy(update={
                "unit_price": Money(amount=price, currency=country.currency),
            })
            countries.append(country.model_copy(update={"new_therapy": therapy}))
        return engine_input.model_copy(update={"countries": tuple(countries)})

    @classmethod
    def _impact_at(
        cls, engine_input: EngineInput, country_code: str, price: float,
    ) -> float:
        result: EngineResult = compute_budget_impact(
            cls._with_price(engine_input, country_code, price)
        )
        country = next(
            c for c in result.countries if c.country_code == country_code
        )
        return country.cumulative_budget_impact.amount

    @classmethod
    def _bisect(
        cls, engine_input: EngineInput, country_code: str, low: float, high: float,
    ) -> float:
        """Standard bisection on a bracket the caller has already verified.

        The bracket is guaranteed to contain a sign change by the checks in
        `break_even`, so this cannot fail to converge — it is separated out
        purely to keep that reasoning in one place and the loop in another.
        """
        for _ in range(_BREAK_EVEN_MAX_ITERATIONS):
            mid = (low + high) / 2.0
            value = cls._impact_at(engine_input, country_code, mid)
            if abs(value) < _BREAK_EVEN_TOLERANCE or (high - low) < _BREAK_EVEN_TOLERANCE:
                return mid
            if value > 0:
                high = mid
            else:
                low = mid
        return (low + high) / 2.0

    # ----------------------------------------------------------------- uptake cases

    @staticmethod
    def uptake_cases(
        build: object, scenario: object,
    ) -> tuple[list[UptakeCaseRead], tuple[Warning_, ...]]:
        """Low, base and high adoption, reported side by side.

        The multipliers are stated constants rather than derived bounds. That
        is the honest framing: nobody publishes an adoption distribution for an
        unlaunched asset, and dressing three assumptions as an interval would
        borrow PSA's credibility for something that has not earned it.
        """
        cases: list[UptakeCaseRead] = []
        warnings: list[Warning_] = []

        for case, multiplier in UPTAKE_SCENARIO_MULTIPLIER.items():
            engine_input, case_warnings = build(  # type: ignore[operator]
                scenario, uptake_multiplier=multiplier,
            )
            result = compute_budget_impact(engine_input)
            final_year_patients = math.fsum(
                country.years[-1].patients_on_new
                for country in result.countries
                if country.years
            )
            cases.append(UptakeCaseRead(
                case=case.value,
                label=UPTAKE_CASE_LABELS[case],
                multiplier=multiplier,
                uptake_terminal=engine_input.uptake.terminal.value,
                by_year=[m.amount for m in result.totals.by_year],
                cumulative=result.totals.cumulative.amount,
                peak_year=result.totals.peak_year,
                patients_treated_final_year=final_year_patients,
                currency=result.totals.cumulative.currency,
            ))
            if case is UptakeScenario.BASE:
                warnings.extend(case_warnings)

        return cases, tuple(warnings)


def aggregate_country_payer(
    country: CountryRead, *, perspective: str, covered_population: int | None,
) -> PayerViewRead | None:
    """One market's payer view, computed from the response rather than re-run.

    Every input it needs — impact, costs and patients per year — is already in
    the country result, so recomputing the engine here would be work for an
    answer already on the table.
    """
    if not country.years:
        return None

    population = float(covered_population) if covered_population else 0.0
    assumed = False
    if population <= 0:
        population = country.funnel[0].value if country.funnel else 0.0
        assumed = Perspective(perspective) in SUBSET_PERSPECTIVES

    impact = [year.budget_impact for year in country.years]
    pmpy = [v / population if population > 0 else 0.0 for v in impact]
    patients = [year.patients_on_new for year in country.years]
    total_patients = math.fsum(patients)

    return PayerViewRead(
        perspective=perspective,
        perspective_label=PERSPECTIVE_LABELS[perspective],
        currency=country.currency,
        covered_population=population,
        covered_population_is_assumed=assumed,
        pmpm_by_year=[v / MONTHS_PER_YEAR for v in pmpy],
        pmpy_by_year=pmpy,
        cumulative_pmpm=(
            country.cumulative_budget_impact / population / MONTHS_PER_YEAR
            / max(len(country.years), 1)
            if population > 0 else 0.0
        ),
        patients_treated_by_year=patients,
        cost_per_treated_patient=(
            country.cumulative_budget_impact / total_patients
            if total_patients > 0 else 0.0
        ),
        total_cost_current_care=[year.cost_without for year in country.years],
        total_cost_with_intervention=[year.cost_with for year in country.years],
    )
