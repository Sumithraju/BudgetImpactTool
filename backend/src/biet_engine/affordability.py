"""Affordability positioning — ARCHITECTURE.md section 5.7, module M8 (forward half).

Positions budget impact against payer capacity: the affordability ratio and
its band classification. The reverse direction — given a ceiling, solve for
the maximum price — is `solver.py`.
"""

from __future__ import annotations

from .constants import AFFORDABILITY_THRESHOLDS, AffordabilityBand
from .exceptions import UnresolvedParameterError
from .funnel import project_population
from .fx import convert
from .models import CountryAffordability, EngineInput, EngineResult, Money


def _band_for(cumulative_ratio: float) -> AffordabilityBand:
    """Highest threshold the ratio meets or exceeds; LOW below the lowest —
    including every negative ratio (a saving), per section 5.1."""
    band = AffordabilityBand.LOW
    for candidate, threshold in AFFORDABILITY_THRESHOLDS.items():
        if cumulative_ratio >= threshold:
            band = candidate
    return band


def compute_affordability(result: EngineResult, inputs: EngineInput) -> tuple[CountryAffordability, ...]:
    """One `CountryAffordability` per market in `inputs`/`result`.

        HealthBudget(c,y)       = health_exp_pc(c) x Pop(c,y)
        AffordabilityRatio(c,y) = BI(c,y) / HealthBudget(c,y)
        cumulative_ratio(c)     = sum_y BI(c,y) / sum_y HealthBudget(c,y)

    `Pop(c,y)` is the projected population from M2's first funnel stage —
    `project_population`, the same formula `compute_funnel` uses — not the
    raw seeded `population_total`, so the denominator grows consistently
    with the numerator. The cumulative ratio is the ratio of sums, not the
    sum of ratios; the two differ whenever the health budget varies across
    years (it doesn't here, since M5 holds costs constant across the
    horizon, but the population it's multiplied by does grow).

    `health_exp_pc` is USD per capita (M0's `health_exp_pc_usd`, sourced from
    World Bank `SH.XPD.CHEX.PC.CD`), so `BI` is converted to USD before the
    ratio is taken — the two must share a currency for the division to be
    dimensionally meaningful, and USD is the one already fixed by the source
    data, not a free choice. `health_budget` is still reported in the
    market's local currency, per this function's own contract — converted
    back from the USD figure used internally, for display next to `BI`
    amounts a reader will see quoted in local currency elsewhere.

    Args:
        result: a forward run's output, from `compute_budget_impact`.
        inputs: the same run's input — `compute_affordability` needs
            `population_total`/`population_growth`/`health_exp_pc`, none of
            which `EngineResult` carries per year.

    Returns:
        One entry per market, in the same order as `inputs.countries`.

    Raises:
        UnresolvedParameterError: a market's `health_exp_pc` is unresolved.
        ValueError: a market's `health_exp_pc` is exactly 0 (division by zero).
    """
    entries = []
    for country_input, country_result in zip(inputs.countries, result.countries, strict=True):
        if country_input.health_exp_pc is None:
            raise UnresolvedParameterError(
                f"health_exp_pc is unresolved for {country_input.country_code}",
                country_code=country_input.country_code,
            )
        health_exp_pc = country_input.health_exp_pc.value
        if health_exp_pc == 0:
            raise ValueError(
                f"health_exp_pc is 0 for {country_input.country_code}; "
                "affordability ratio is undefined"
            )

        ratios: list[float] = []
        bi_usd_sum = 0.0
        budget_usd_sum = 0.0
        for index, year_result in enumerate(country_result.years):
            year = index + 1
            pop = project_population(
                country_input.population_total, country_input.population_growth, year,
            )
            health_budget_usd = health_exp_pc * pop
            bi_usd = convert(year_result.budget_impact, "USD", inputs.fx_rates).amount

            ratios.append(bi_usd / health_budget_usd)
            bi_usd_sum += bi_usd
            budget_usd_sum += health_budget_usd

        cumulative_ratio = bi_usd_sum / budget_usd_sum
        health_budget_local = convert(
            Money(amount=budget_usd_sum, currency="USD"), country_input.currency, inputs.fx_rates,
        )

        entries.append(
            CountryAffordability(
                country_code=country_input.country_code,
                health_budget=health_budget_local,
                ratio_by_year=tuple(ratios),
                cumulative_ratio=cumulative_ratio,
                band=_band_for(cumulative_ratio),
            )
        )

    return tuple(entries)
